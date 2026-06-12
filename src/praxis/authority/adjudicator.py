"""Authority adjudication for source-backed claims."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path

from .models import AdjudicationRequest, AdjudicationResult, canonical_json, parse_timestamp, stable_hash, utc_now
from .registry import active_bundle_record, connect, list_anchors


def select_anchor(root: Path, request: AdjudicationRequest):
    anchors = [anchor for anchor in list_anchors(root) if anchor.matches(request)]
    if not anchors:
        return None
    return sorted(anchors, key=lambda anchor: (-anchor.specificity(), anchor.anchor_id))[0]


def _is_stale(fresh_at: str, freshness_sla_hours: int, now: datetime) -> tuple[bool, str]:
    timestamp = parse_timestamp(fresh_at)
    if timestamp is None:
        return True, "missing_or_invalid_fresh_at"
    age_hours = max((now - timestamp).total_seconds() / 3600.0, 0.0)
    if age_hours > freshness_sla_hours:
        return True, f"stale:{age_hours:.1f}h>{freshness_sla_hours}h"
    return False, f"fresh:{age_hours:.1f}h<={freshness_sla_hours}h"


def _missing_required_evidence(request: AdjudicationRequest, required: list[str]) -> list[str]:
    missing: list[str] = []
    for field in required:
        if field == "evidence_id" and not request.evidence_id:
            missing.append(field)
        elif field not in {"evidence_id"} and not request.metadata.get(field):
            missing.append(field)
    return missing


def adjudicate_request(
    root: Path,
    request: AdjudicationRequest,
    *,
    actor: str = "system",
    write_record: bool = True,
    now: datetime | None = None,
) -> AdjudicationResult:
    """Evaluate a claim source against the active authority registry."""

    now = now or datetime.now(timezone.utc)
    record = active_bundle_record(root)
    bundle_id = str(record["bundle_id"]) if record else ""
    bundle_hash = str(record["bundle_hash"]) if record else ""
    anchor = select_anchor(root, request)

    if anchor is None:
        result = AdjudicationResult(
            decision="unknown",
            reason="no matching authority anchor",
            bundle_id=bundle_id,
            bundle_hash=bundle_hash,
            safe_default="treat_as_context",
        )
    else:
        missing = _missing_required_evidence(request, anchor.required_evidence)
        stale, freshness_reason = _is_stale(request.fresh_at, anchor.freshness_sla_hours, now)
        if request.source in anchor.forbidden_sources:
            decision = "block"
            reason = f"source is forbidden for this claim scope: {request.source}"
        elif missing:
            decision = "block" if "block" in anchor.conflict_behavior else "warn"
            reason = "missing required evidence: " + ", ".join(missing)
        elif request.source == anchor.authoritative_source:
            decision = "warn" if stale else "allow"
            reason = freshness_reason
        elif request.source in anchor.fallback_sources:
            decision = "warn"
            reason = f"fallback source used; {freshness_reason}"
        else:
            decision = "block" if "block" in anchor.conflict_behavior else "warn"
            reason = f"source is not authoritative for this claim scope: {request.source}"

        result = AdjudicationResult(
            decision=decision,
            reason=reason,
            anchor_id=anchor.anchor_id,
            bundle_id=bundle_id,
            bundle_hash=bundle_hash,
            safe_default=anchor.safe_default,
            details={
                "authoritative_source": anchor.authoritative_source,
                "freshness": freshness_reason,
                "conflict_behavior": anchor.conflict_behavior,
            },
        )

    if write_record:
        write_adjudication_record(root, request, result, actor=actor)
    return result


def write_adjudication_record(
    root: Path,
    request: AdjudicationRequest,
    result: AdjudicationResult,
    *,
    actor: str,
) -> str:
    created_at = utc_now().isoformat()
    request_hash = stable_hash(request.to_dict())
    record_id = "adjudication:" + stable_hash({"request": request.to_dict(), "created_at": created_at})[:16]
    with connect(root) as connection:
        try:
            connection.execute(
                """
                INSERT INTO adjudication_records
                (record_id, request_hash, claim_type, source, client_id, evidence_id, decision, reason,
                 anchor_id, bundle_id, bundle_hash, created_at, actor, request_json, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    request_hash,
                    request.claim_type,
                    request.source,
                    request.client_id,
                    request.evidence_id,
                    result.decision,
                    result.reason,
                    result.anchor_id,
                    result.bundle_id,
                    result.bundle_hash,
                    created_at,
                    actor,
                    canonical_json(request.to_dict()),
                    canonical_json(result.to_dict()),
                ),
            )
        except sqlite3.IntegrityError:
            pass
    return record_id


def list_adjudication_records(root: Path, *, limit: int = 20) -> list[dict[str, str]]:
    with connect(root) as connection:
        rows = connection.execute(
            """
            SELECT record_id, claim_type, source, decision, reason, anchor_id, created_at
            FROM adjudication_records
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def show_adjudication_record(root: Path, record_id: str) -> dict[str, object] | None:
    with connect(root) as connection:
        row = connection.execute(
            "SELECT * FROM adjudication_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
    if row is None:
        return None
    payload = dict(row)
    payload["request"] = json.loads(payload.pop("request_json"))
    payload["result"] = json.loads(payload.pop("result_json"))
    return payload
