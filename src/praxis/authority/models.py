"""Data models for Praxis authority anchors.

The internal package intentionally uses neutral names so the product surface can
change later without renaming every table and field.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


Decision = str


def canonical_json(data: Any) -> str:
    """Return stable JSON for hashing and audit records."""

    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
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


@dataclass(frozen=True)
class TruthAnchor:
    """A rule that identifies the source of record for a claim scope."""

    anchor_id: str
    scope: dict[str, Any]
    authoritative_source: str
    fallback_sources: list[str] = field(default_factory=list)
    forbidden_sources: list[str] = field(default_factory=list)
    freshness_sla_hours: int = 720
    conflict_behavior: str = "warn_and_report"
    required_evidence: list[str] = field(default_factory=list)
    safe_default: str = "treat_as_context"
    status: str = "active"
    description: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TruthAnchor":
        return cls(
            anchor_id=str(payload.get("id") or payload.get("anchor_id") or ""),
            scope=dict(payload.get("scope") or {}),
            authoritative_source=str(payload.get("authoritative_source") or ""),
            fallback_sources=[str(item) for item in payload.get("fallback_sources", [])],
            forbidden_sources=[str(item) for item in payload.get("forbidden_sources", [])],
            freshness_sla_hours=int(payload.get("freshness_sla_hours", 720)),
            conflict_behavior=str(payload.get("conflict_behavior") or "warn_and_report"),
            required_evidence=[str(item) for item in payload.get("required_evidence", [])],
            safe_default=str(payload.get("safe_default") or "treat_as_context"),
            status=str(payload.get("status") or "active"),
            description=str(payload.get("description") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["id"] = payload.pop("anchor_id")
        return payload

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.anchor_id:
            errors.append("anchor id is required")
        if not self.scope:
            errors.append(f"{self.anchor_id}: scope is required")
        if not self.authoritative_source:
            errors.append(f"{self.anchor_id}: authoritative_source is required")
        if self.freshness_sla_hours <= 0:
            errors.append(f"{self.anchor_id}: freshness_sla_hours must be positive")
        return errors

    def matches(self, request: "AdjudicationRequest") -> bool:
        if self.status != "active":
            return False
        for key, expected in self.scope.items():
            actual = request.scope_value(key)
            if expected == "*":
                continue
            if str(actual or "") != str(expected):
                return False
        return True

    def specificity(self) -> int:
        return sum(1 for value in self.scope.values() if value != "*")


@dataclass(frozen=True)
class InvariantRule:
    invariant_id: str
    summary: str
    severity: str = "medium"
    status: str = "active"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InvariantRule":
        return cls(
            invariant_id=str(payload.get("id") or payload.get("invariant_id") or ""),
            summary=str(payload.get("summary") or ""),
            severity=str(payload.get("severity") or "medium"),
            status=str(payload.get("status") or "active"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["id"] = payload.pop("invariant_id")
        return payload


@dataclass(frozen=True)
class AuthorityBundle:
    bundle_id: str
    version: int
    anchors: list[TruthAnchor]
    invariants: list[InvariantRule] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AuthorityBundle":
        return cls(
            bundle_id=str(payload.get("bundle_id") or payload.get("id") or "bundle:default"),
            version=int(payload.get("version", 1)),
            anchors=[TruthAnchor.from_dict(item) for item in payload.get("anchors", [])],
            invariants=[InvariantRule.from_dict(item) for item in payload.get("invariants", [])],
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "version": self.version,
            "anchors": [anchor.to_dict() for anchor in self.anchors],
            "invariants": [rule.to_dict() for rule in self.invariants],
            "metadata": self.metadata,
        }

    def bundle_hash(self) -> str:
        return stable_hash(self.to_dict())

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.bundle_id:
            errors.append("bundle_id is required")
        if self.version <= 0:
            errors.append("version must be positive")
        seen: set[str] = set()
        for anchor in self.anchors:
            errors.extend(anchor.validate())
            if anchor.anchor_id in seen:
                errors.append(f"duplicate anchor id: {anchor.anchor_id}")
            seen.add(anchor.anchor_id)
        return errors


@dataclass(frozen=True)
class AdjudicationRequest:
    claim_type: str
    source: str
    client_id: str = ""
    evidence_id: str = ""
    fresh_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def scope_value(self, key: str) -> Any:
        if key == "claim_type":
            return self.claim_type
        if key == "source":
            return self.source
        if key == "client_id":
            return self.client_id
        return self.metadata.get(key)


@dataclass(frozen=True)
class AdjudicationResult:
    decision: Decision
    reason: str
    anchor_id: str = ""
    bundle_id: str = ""
    bundle_hash: str = ""
    safe_default: str = "treat_as_context"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
