"""Boring, reusable models for Praxis Core governance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


Decision = str
Severity = str


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    exists: bool
    source_kind: str = ""
    status: str = ""
    client_id: str = ""
    fresh_at: str = ""
    sources: list[str] = field(default_factory=list)
    path: str = ""
    warnings: list[str] = field(default_factory=list)
    resolved_entity_ids: list[str] = field(default_factory=list)
    entity_resolution_status: str = ""
    entity_resolution_confidence: float = 0.0
    entity_resolution_method: str = ""
    unresolved_mentions: list[str] = field(default_factory=list)
    ambiguous_entity_candidates: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reasons: list[str]
    evidence: EvidenceRef | None = None
    authority_decision: str = ""
    authority_reason: str = ""
    conflict_count: int = 0
    severity: Severity = "info"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence"] = self.evidence.to_dict() if self.evidence else None
        return payload


@dataclass(frozen=True)
class GovernanceEvent:
    event_type: str
    actor: str
    payload: dict[str, Any]
    decision: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernanceReceipt:
    event_id: str
    event_type: str
    payload_hash: str
    previous_hash: str
    receipt_hash: str
    created_at: str
    actor: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernanceCheck:
    check_id: str
    severity: Severity
    status: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
