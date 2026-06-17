"""SQLite storage for Praxis relationship evidence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from praxis.entities.storage import annotation_by_id, connect_entity_db, json_dumps, normalize_entity_text, stable_id

from .identifiers import relation_key, text_entity_id
from .models import AcceptedEdge, RelationClaim
from .schema import ensure_relationship_evidence_schema


def connect_relationship_evidence_db(db_path: Path) -> sqlite3.Connection:
    connection = connect_entity_db(db_path)
    ensure_relationship_evidence_schema(connection)
    return connection


def claim_from_candidate(row: sqlite3.Row) -> RelationClaim:
    metadata = json.loads(row["metadata_json"] or "{}")
    return RelationClaim(
        subject_text=str(metadata.get("subject_text") or row["subject_entity_id"] or ""),
        subject_entity_id=str(row["subject_entity_id"] or ""),
        subject_type=str(metadata.get("subject_type") or "unknown"),
        predicate=str(row["predicate"] or ""),
        object_value=str(row["object_value"] or metadata.get("object_text") or ""),
        object_entity_id=str(row["object_entity_id"] or ""),
        object_type=str(metadata.get("object_type") or "unknown"),
        chunk_id=str(row["chunk_id"] or ""),
        evidence_annotation_id=str(row["evidence_annotation_id"] or ""),
        confidence=float(row["confidence"] or 0.0),
        extractor=str(row["extractor"] or ""),
        metadata=metadata,
    )


def subject_id_for_claim(claim: RelationClaim) -> str:
    return claim.subject_entity_id or text_entity_id(claim.subject_text, claim.subject_type)


def object_id_for_claim(claim: RelationClaim) -> str:
    if claim.object_entity_id:
        return claim.object_entity_id
    if claim.object_type == "unknown":
        return ""
    return text_entity_id(claim.object_value, claim.object_type)


def relation_metadata(claim: RelationClaim) -> dict[str, Any]:
    return {
        **claim.metadata,
        "subject_text": claim.subject_text,
        "subject_type": claim.subject_type,
        "object_type": claim.object_type,
        "relation_key": relation_key(claim.subject_text, claim.predicate, claim.object_value),
    }


def upsert_relation_candidate(connection: sqlite3.Connection, claim: RelationClaim) -> str:
    subject_id = subject_id_for_claim(claim)
    object_id = object_id_for_claim(claim)
    candidate_id = stable_id(
        "relation-candidate",
        [
            subject_id,
            claim.predicate,
            object_id,
            normalize_entity_text(claim.object_value),
            claim.chunk_id,
            claim.evidence_annotation_id,
        ],
    )
    connection.execute(
        """
        INSERT INTO relation_candidates(
          id, subject_entity_id, predicate, object_entity_id, object_value, chunk_id,
          evidence_annotation_id, confidence, status, extractor, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          predicate=excluded.predicate,
          object_value=excluded.object_value,
          confidence=excluded.confidence,
          extractor=excluded.extractor,
          evidence_annotation_id=excluded.evidence_annotation_id,
          metadata_json=excluded.metadata_json,
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            candidate_id,
            subject_id,
            claim.predicate,
            object_id,
            claim.object_value,
            claim.chunk_id,
            claim.evidence_annotation_id,
            claim.confidence,
            claim.extractor,
            json_dumps(relation_metadata(claim)),
        ),
    )
    return candidate_id


def iter_relation_candidates(
    connection: sqlite3.Connection,
    *,
    status: str = "candidate",
    limit: int = 0,
) -> list[sqlite3.Row]:
    params: list[Any] = []
    where = ""
    if status:
        where = "WHERE status = ?"
        params.append(status)
    limit_clause = ""
    if limit:
        limit_clause = "LIMIT ?"
        params.append(limit)
    return connection.execute(
        f"""
        SELECT *
        FROM relation_candidates
        {where}
        ORDER BY confidence DESC, created_at, id
        {limit_clause}
        """,
        params,
    ).fetchall()


def upsert_accepted_edge(
    connection: sqlite3.Connection,
    *,
    candidate_id: str,
    claim: RelationClaim,
    ontology_id: str,
    ontology_version: str,
    status: str = "accepted",
) -> str:
    subject_id = subject_id_for_claim(claim)
    object_id = object_id_for_claim(claim)
    edge_id = stable_id(
        "graph-edge",
        [
            subject_id,
            claim.predicate,
            object_id,
            normalize_entity_text(claim.object_value),
            candidate_id,
        ],
    )
    connection.execute(
        """
        INSERT INTO accepted_graph_edges(
          id, subject_entity_id, subject_text, subject_type, predicate, object_entity_id,
          object_value, object_type, confidence, status, ontology_id, ontology_version,
          source_relation_candidate_id, evidence_annotation_id, chunk_id, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(subject_entity_id, predicate, object_entity_id, object_value, source_relation_candidate_id)
        DO UPDATE SET
          subject_text=excluded.subject_text,
          subject_type=excluded.subject_type,
          object_type=excluded.object_type,
          confidence=excluded.confidence,
          status=excluded.status,
          ontology_id=excluded.ontology_id,
          ontology_version=excluded.ontology_version,
          evidence_annotation_id=excluded.evidence_annotation_id,
          chunk_id=excluded.chunk_id,
          metadata_json=excluded.metadata_json,
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            edge_id,
            subject_id,
            claim.subject_text,
            claim.subject_type,
            claim.predicate,
            object_id,
            claim.object_value,
            claim.object_type,
            claim.confidence,
            status,
            ontology_id,
            ontology_version,
            candidate_id,
            claim.evidence_annotation_id,
            claim.chunk_id,
            json_dumps(relation_metadata(claim)),
        ),
    )
    if claim.evidence_annotation_id:
        connection.execute(
            """
            INSERT OR IGNORE INTO accepted_graph_edge_evidence(edge_id, evidence_annotation_id, chunk_id, role)
            VALUES (?, ?, ?, 'supporting')
            """,
            (edge_id, claim.evidence_annotation_id, claim.chunk_id),
        )
    return edge_id


def set_candidate_status(connection: sqlite3.Connection, candidate_id: str, status: str) -> None:
    connection.execute(
        "UPDATE relation_candidates SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, candidate_id),
    )


def set_annotation_status(connection: sqlite3.Connection, annotation_id: str, status: str) -> None:
    if not annotation_id:
        return
    connection.execute(
        "UPDATE evidence_annotations SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, annotation_id),
    )


def add_review_item(
    connection: sqlite3.Connection,
    *,
    object_type: str,
    object_id: str,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    review_id = stable_id("relationship-review", [object_type, object_id, reason])
    connection.execute(
        """
        INSERT INTO relationship_evidence_review_items(object_type, object_id, reason, metadata_json, id)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          reason=excluded.reason,
          metadata_json=excluded.metadata_json,
          updated_at=CURRENT_TIMESTAMP
        """,
        (object_type, object_id, reason, json_dumps(metadata or {}), review_id),
    )
    return review_id


def accepted_edge_conflict_exists(connection: sqlite3.Connection, claim: RelationClaim) -> bool:
    subject_id = subject_id_for_claim(claim)
    row = connection.execute(
        """
        SELECT id
        FROM accepted_graph_edges
        WHERE subject_entity_id = ?
          AND predicate = ?
          AND status = 'accepted'
          AND lower(object_value) != lower(?)
        LIMIT 1
        """,
        (subject_id, claim.predicate, claim.object_value),
    ).fetchone()
    return row is not None


def edge_from_row(row: sqlite3.Row) -> AcceptedEdge:
    metadata = json.loads(row["metadata_json"] or "{}")
    return AcceptedEdge(
        id=str(row["id"]),
        subject_entity_id=str(row["subject_entity_id"] or ""),
        subject_text=str(row["subject_text"] or ""),
        subject_type=str(row["subject_type"] or "unknown"),
        predicate=str(row["predicate"] or ""),
        object_entity_id=str(row["object_entity_id"] or ""),
        object_value=str(row["object_value"] or ""),
        object_type=str(row["object_type"] or "unknown"),
        confidence=float(row["confidence"] or 0.0),
        status=str(row["status"] or ""),
        ontology_id=str(row["ontology_id"] or ""),
        ontology_version=str(row["ontology_version"] or ""),
        source_relation_candidate_id=str(row["source_relation_candidate_id"] or ""),
        evidence_annotation_id=str(row["evidence_annotation_id"] or ""),
        chunk_id=str(row["chunk_id"] or ""),
        metadata=metadata,
    )


def parsed_annotation(connection: sqlite3.Connection, annotation_id: str) -> dict[str, Any] | None:
    row = annotation_by_id(connection, annotation_id)
    if row is None:
        return None
    payload = dict(row)
    for key, default in (
        ("source_chunk_ids_json", []),
        ("resolved_entity_ids_json", []),
        ("extracted_json", {}),
        ("governance_json", {}),
    ):
        out_key = key.removesuffix("_json")
        try:
            payload[out_key] = json.loads(payload.get(key) or json_dumps(default))
        except json.JSONDecodeError:
            payload[out_key] = default
    return payload
