"""Unified context-priority scoring for Praxis retrieval results."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


CONFIDENCE_SCORES = {
    "high": 1.0,
    "medium": 0.7,
    "low": 0.35,
    "unknown": 0.5,
    "": 0.5,
}

STATUS_SCORES = {
    "active": 1.0,
    "accepted": 1.0,
    "provisional": 0.75,
    "proposed": 0.65,
    "new": 0.65,
    "stale_pending_refresh": 0.45,
    "acknowledged": 0.45,
    "deprecated": 0.0,
    "reverted": 0.0,
    "merged": 0.0,
    "suppressed": 0.0,
    "resolved": 0.0,
}

SEVERITY_PENALTIES = {
    "high": 0.35,
    "medium": 0.22,
    "low": 0.12,
}


@dataclass(frozen=True)
class ContextPriorityBreakdown:
    """Transparent components behind one context-priority score."""

    priority: float
    relevance: float
    trust: float
    freshness: float
    graph: float
    status: float
    conflict_penalty: float
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def row_get(row: Mapping[str, Any] | Any | None, key: str, default: Any = "") -> Any:
    if row is None:
        return default
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        return row[key]
    except (IndexError, KeyError, TypeError):
        return default


def confidence_score(value: Any) -> float:
    return CONFIDENCE_SCORES.get(str(value or "").strip().lower(), CONFIDENCE_SCORES["unknown"])


def status_score(value: Any) -> float:
    return STATUS_SCORES.get(str(value or "").strip().lower(), 0.55)


def credibility_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.5
    return clamp(score / 5.0)


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    if " " in text and "T" not in text:
        candidates.append(text.replace(" ", "T"))
        candidates.append(text.replace(" ", "T") + "+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def freshness_score(source: Mapping[str, Any] | Any | None, *, now: datetime | None = None) -> tuple[float, str]:
    checked_at = parse_timestamp(row_get(source, "last_checked_at") or row_get(source, "updated_at") or row_get(source, "created_at"))
    if checked_at is None:
        return 0.55, "freshness:unknown"
    now = now or datetime.now(timezone.utc)
    try:
        window_days = int(row_get(source, "freshness_window_days", 30) or 30)
    except (TypeError, ValueError):
        window_days = 30
    window_days = max(window_days, 1)
    age_days = max((now - checked_at).total_seconds() / 86400.0, 0.0)
    if age_days <= window_days:
        return 1.0, f"freshness:fresh({age_days:.1f}d/{window_days}d)"
    if age_days <= window_days * 2:
        return 0.65, f"freshness:aging({age_days:.1f}d/{window_days}d)"
    return 0.25, f"freshness:stale({age_days:.1f}d/{window_days}d)"


def conflict_penalty(conflicts: Iterable[Mapping[str, Any] | Any]) -> tuple[float, str]:
    total = 0.0
    count = 0
    high = 0
    for conflict in conflicts:
        status = str(row_get(conflict, "status", "open") or "open").lower()
        if status not in {"open", "acknowledged"}:
            continue
        count += 1
        severity = str(row_get(conflict, "severity", "medium") or "medium").lower()
        penalty = SEVERITY_PENALTIES.get(severity, SEVERITY_PENALTIES["medium"])
        if status == "acknowledged":
            penalty *= 0.6
        if severity == "high":
            high += 1
        total += penalty
    if count == 0:
        return 0.0, "conflicts:none"
    capped = clamp(total, 0.0, 0.55)
    detail = f"conflicts:{count}"
    if high:
        detail += f",high={high}"
    return capped, f"{detail},penalty={capped:.3f}"


def trust_score(row: Mapping[str, Any] | Any, source: Mapping[str, Any] | Any | None) -> tuple[float, str]:
    chunk_confidence = confidence_score(row_get(row, "confidence", "medium"))
    source_confidence = credibility_score(row_get(source, "credibility_score", None))
    if source is None:
        trust = chunk_confidence
        reason = f"trust:chunk_confidence={chunk_confidence:.3f}"
    else:
        trust = (chunk_confidence * 0.55) + (source_confidence * 0.45)
        reason = f"trust:chunk={chunk_confidence:.3f},source={source_confidence:.3f}"
    return clamp(trust), reason


def combined_status_score(row: Mapping[str, Any] | Any, source: Mapping[str, Any] | Any | None) -> tuple[float, str]:
    chunk_status = status_score(row_get(row, "status", "active"))
    source_status = status_score(row_get(source, "status", "active")) if source is not None else 1.0
    status = min(chunk_status, source_status)
    return status, f"status:chunk={chunk_status:.3f},source={source_status:.3f}"


def score_context_priority(
    *,
    relevance: float,
    row: Mapping[str, Any] | Any,
    source: Mapping[str, Any] | Any | None = None,
    graph: float = 0.0,
    conflicts: Iterable[Mapping[str, Any] | Any] = (),
) -> ContextPriorityBreakdown:
    """Score how useful a context candidate should be for agent work.

    Retrieval relevance stays dominant, but priority also accounts for whether
    the candidate is trusted, fresh, graph-connected, live, and conflict-free.
    """

    normalized_relevance = clamp(float(relevance or 0.0))
    normalized_graph = clamp(float(graph or 0.0))
    trust, trust_reason = trust_score(row, source)
    freshness, freshness_reason = freshness_score(source)
    status, status_reason = combined_status_score(row, source)
    penalty, conflict_reason = conflict_penalty(conflicts)
    priority = clamp(
        (0.55 * normalized_relevance)
        + (0.15 * trust)
        + (0.10 * freshness)
        + (0.10 * normalized_graph)
        + (0.10 * status)
        - penalty
    )
    reasons = [
        f"relevance:{normalized_relevance:.3f}",
        trust_reason,
        freshness_reason,
        f"graph:{normalized_graph:.3f}",
        status_reason,
        conflict_reason,
    ]
    return ContextPriorityBreakdown(
        priority=priority,
        relevance=normalized_relevance,
        trust=trust,
        freshness=freshness,
        graph=normalized_graph,
        status=status,
        conflict_penalty=penalty,
        reasons=reasons,
    )
