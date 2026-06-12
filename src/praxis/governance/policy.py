"""Deterministic Core governance policy evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from praxis.authority.adjudicator import adjudicate_request
from praxis.authority.models import AdjudicationRequest

from .evidence import evidence_conflict_count, evidence_has_active_status, infer_source_from_evidence, validate_evidence_ref
from .models import GovernanceEvent, PolicyResult
from .storage import record_event


def _worst(current: str, candidate: str) -> str:
    order = {"allow": 0, "warn": 1, "require_review": 2, "block": 3}
    return candidate if order[candidate] > order[current] else current


def evaluate_policy(
    root: Path,
    *,
    claim_type: str,
    evidence_id: str,
    source: str = "",
    client_id: str = "",
    fresh_at: str = "",
    metadata: dict[str, Any] | None = None,
    actor: str = "praxis",
    write_record: bool = True,
) -> PolicyResult:
    """Evaluate whether evidence can be reused for a claim/action."""

    reasons: list[str] = []
    metadata = dict(metadata or {})
    evidence = validate_evidence_ref(root, evidence_id)
    decision = "allow"
    severity = "info"
    if not evidence.exists:
        decision = "block"
        severity = "error"
        reasons.extend(evidence.warnings)
    else:
        if not evidence_has_active_status(evidence):
            decision = _worst(decision, "warn")
            severity = "warn"
            reasons.append(f"evidence status is not active: {evidence.status}")
        if evidence.warnings:
            decision = _worst(decision, "warn")
            severity = "warn"
            reasons.extend(f"evidence warning: {warning}" for warning in evidence.warnings[:5])

        if evidence.source_kind == "evidence_annotation":
            if evidence.entity_resolution_status not in {"accepted", "active"}:
                decision = _worst(decision, "require_review")
                severity = "warn" if severity != "error" else severity
                reasons.append(f"entity resolution requires review: {evidence.entity_resolution_status or 'unknown'}")
            if evidence.ambiguous_entity_candidates:
                decision = _worst(decision, "require_review")
                severity = "warn" if severity != "error" else severity
                reasons.append("entity evidence has ambiguous candidates")
            if not evidence.resolved_entity_ids:
                decision = _worst(decision, "require_review")
                severity = "warn" if severity != "error" else severity
                reasons.append("entity evidence has no resolved entity ids")

    source = source or infer_source_from_evidence(evidence)
    fresh_at = fresh_at or evidence.fresh_at
    client_id = client_id or evidence.client_id
    authority = adjudicate_request(
        root,
        AdjudicationRequest(
            claim_type=claim_type,
            source=source,
            client_id=client_id,
            evidence_id=evidence_id,
            fresh_at=fresh_at,
            metadata=metadata,
        ),
        actor=actor,
        write_record=write_record,
    )
    if authority.decision == "block":
        decision = "block"
        severity = "error"
        reasons.append(f"authority blocked: {authority.reason}")
    elif authority.decision in {"warn", "unknown"}:
        decision = _worst(decision, "warn")
        severity = "warn" if severity != "error" else severity
        reasons.append(f"authority {authority.decision}: {authority.reason}")
    else:
        reasons.append(f"authority allow: {authority.reason}")

    conflict_count = evidence_conflict_count(evidence)
    if conflict_count:
        decision = _worst(decision, "warn")
        severity = "warn" if severity != "error" else severity
        reasons.append(f"evidence has {conflict_count} conflict record(s)")

    result = PolicyResult(
        decision=decision,
        reasons=reasons or ["policy evaluation passed"],
        evidence=evidence,
        authority_decision=authority.decision,
        authority_reason=authority.reason,
        conflict_count=conflict_count,
        severity=severity,
        metadata={
            "claim_type": claim_type,
            "source": source,
            "client_id": client_id,
            "fresh_at": fresh_at,
            "authority_anchor_id": authority.anchor_id,
            "authority_bundle_hash": authority.bundle_hash,
        },
    )
    if write_record:
        record_event(
            root,
            GovernanceEvent(
                event_type="policy_evaluation",
                actor=actor,
                decision=result.decision,
                payload=result.to_dict(),
            ),
        )
    return result


def search_result_governance_warnings(row: Any) -> list[str]:
    warnings: list[str] = []
    try:
        source_id = row["source_id"]
        capture_id = row["capture_id"]
    except (KeyError, TypeError, IndexError):
        return warnings
    if source_id and not capture_id:
        warnings.append("governance: result has a source_id but no capture_id; provenance may be incomplete")
    if not source_id:
        warnings.append("governance: result has no source_id; validate before using as durable knowledge")
    return warnings
