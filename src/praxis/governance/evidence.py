"""Evidence-reference validation for Praxis Core governance."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from praxis.entities.retrieval import annotation_payload
from praxis.paths import kg_dir, vectors_dir
from praxis.reach.storage import evidence_dir, read_json

from .models import EvidenceRef


LIVE_STATUSES = {"active", "accepted", "fresh", "ok", "not_required", ""}
INACTIVE_STATUSES = {"deprecated", "reverted", "suppressed", "deleted", "missing", "conflicted", "partial_conflicted"}


def _reach_evidence(root: Path, evidence_id: str) -> EvidenceRef | None:
    directory = evidence_dir(root)
    if not directory.exists():
        return None
    for path in directory.glob("*.json"):
        try:
            payload = read_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        if payload.get("evidence_id") != evidence_id:
            continue
        warnings = [str(item) for item in payload.get("warnings", [])]
        warnings.extend(str(item) for item in payload.get("conflicts", []))
        return EvidenceRef(
            evidence_id=evidence_id,
            exists=True,
            source_kind="reach_evidence",
            status=str(payload.get("data_quality_status") or payload.get("freshness_status") or "ok"),
            client_id=str(payload.get("client_id") or ""),
            fresh_at=str(payload.get("fresh_at") or ""),
            sources=[str(item) for item in payload.get("sources", [])],
            path=str(path),
            warnings=warnings,
            metadata={
                "query_id": payload.get("query_id", ""),
                "freshness_status": payload.get("freshness_status", ""),
                "data_quality_status": payload.get("data_quality_status", ""),
                "confidence_score": payload.get("confidence_score", ""),
                "conflict_records": payload.get("conflict_records", []),
                "metric_sources": payload.get("metric_sources", {}),
            },
        )


def _skill_graph_evidence(root: Path, evidence_id: str) -> EvidenceRef | None:
    db_path = kg_dir(root) / "skill_graph.sqlite"
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,)).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return EvidenceRef(
        evidence_id=evidence_id,
        exists=True,
        source_kind="skill_graph_evidence",
        status=str(row["status"] or "active"),
        fresh_at=str(row["updated_at"] or row["created_at"] or ""),
        sources=[str(row["url"] or row["source_path"] or row["evidence_type"])],
        path=str(db_path),
        warnings=[],
        metadata={
            "title": row["title"],
            "evidence_type": row["evidence_type"],
            "confidence": row["confidence"],
            "locator": row["locator"],
        },
    )


def _entity_annotation(root: Path, evidence_id: str) -> EvidenceRef | None:
    db_path = vectors_dir(root) / "semantic_index.sqlite"
    try:
        payload = annotation_payload(db_path, evidence_id)
    except (OSError, sqlite3.Error):
        return None
    if not payload:
        return None
    governance = payload.get("governance") if isinstance(payload.get("governance"), dict) else {}
    extracted = payload.get("extracted") if isinstance(payload.get("extracted"), dict) else {}
    resolved_entity_ids = [str(item) for item in payload.get("resolved_entity_ids", [])]
    status = str(payload.get("status") or "candidate")
    resolution_status = str(governance.get("entity_resolution_status") or status)
    warnings: list[str] = []
    if resolution_status not in {"accepted", "active"}:
        warnings.append(f"entity resolution is not accepted: {resolution_status}")
    ambiguous = [str(item) for item in governance.get("ambiguous_entity_candidates", [])] if isinstance(governance.get("ambiguous_entity_candidates"), list) else []
    unresolved = [str(item) for item in governance.get("unresolved_mentions", [])] if isinstance(governance.get("unresolved_mentions"), list) else []
    if ambiguous:
        warnings.append("entity evidence has ambiguous candidates")
    if unresolved:
        warnings.append("entity evidence has unresolved mentions")
    return EvidenceRef(
        evidence_id=evidence_id,
        exists=True,
        source_kind="evidence_annotation",
        status=status,
        sources=["entity_annotation"],
        path=str(db_path),
        warnings=warnings,
        resolved_entity_ids=resolved_entity_ids,
        entity_resolution_status=resolution_status,
        entity_resolution_confidence=float(governance.get("entity_resolution_confidence") or payload.get("confidence") or 0.0),
        entity_resolution_method=str(governance.get("entity_resolution_method") or ""),
        unresolved_mentions=unresolved,
        ambiguous_entity_candidates=ambiguous,
        metadata={
            "annotation_type": payload.get("annotation_type", ""),
            "source_chunk_ids": payload.get("source_chunk_ids", []),
            "extractor": payload.get("extractor", ""),
            "extracted": extracted,
            "governance": governance,
        },
    )


def validate_evidence_ref(root: Path, evidence_id: str) -> EvidenceRef:
    if not evidence_id:
        return EvidenceRef(evidence_id="", exists=False, status="missing", warnings=["evidence_id is required"])
    found = _reach_evidence(root, evidence_id) or _skill_graph_evidence(root, evidence_id) or _entity_annotation(root, evidence_id)
    if found:
        return found
    return EvidenceRef(
        evidence_id=evidence_id,
        exists=False,
        status="missing",
        warnings=[f"evidence not found: {evidence_id}"],
    )


def evidence_has_active_status(evidence: EvidenceRef) -> bool:
    status = (evidence.status or "").strip().lower()
    if status in LIVE_STATUSES:
        return True
    if status in INACTIVE_STATUSES:
        return False
    return False


def evidence_conflict_count(evidence: EvidenceRef) -> int:
    conflict_records = evidence.metadata.get("conflict_records")
    if isinstance(conflict_records, list):
        return len(conflict_records)
    return 0


def infer_source_from_evidence(evidence: EvidenceRef) -> str:
    if len(evidence.sources) == 1:
        return evidence.sources[0]
    if evidence.source_kind == "reach_evidence":
        return "evidence_card"
    if evidence.source_kind == "skill_graph_evidence":
        return "accepted_note"
    if evidence.source_kind == "evidence_annotation":
        return "entity_annotation"
    return ""
