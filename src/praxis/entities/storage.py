"""Storage helpers for entity mentions, resolution candidates, and evidence annotations."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from praxis.commands.vector_common import connect as connect_vector
from praxis.commands.vector_common import ensure_schema as ensure_vector_schema
from praxis.commands.vector_common import sha256_text, utc_now
from praxis.paths import default_root, kg_dir, vectors_dir


DEFAULT_ROOT = default_root()
DEFAULT_VECTOR_DB = vectors_dir(DEFAULT_ROOT) / "semantic_index.sqlite"
DEFAULT_KG_DB = kg_dir(DEFAULT_ROOT) / "skill_graph.sqlite"

ACTIVE_NODE_STATUSES = ("active", "provisional")
ACCEPTED_MENTION_STATUSES = ("accepted", "active")


def normalize_entity_text(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    tokens = [
        token
        for token in normalized.split()
        if token not in {"the", "a", "an", "inc", "llc", "ltd", "corp", "corporation", "co", "company"}
    ]
    return " ".join(tokens)


def stable_id(prefix: str, parts: Iterable[str]) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ensure_entity_schema(connection: sqlite3.Connection) -> None:
    ensure_vector_schema(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS entity_extraction_runs (
          id TEXT PRIMARY KEY,
          scope TEXT NOT NULL DEFAULT '',
          extractor TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'running',
          started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          completed_at TEXT,
          metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS entity_mentions (
          id TEXT PRIMARY KEY,
          chunk_id TEXT NOT NULL REFERENCES semantic_chunks(id) ON DELETE CASCADE,
          document_id TEXT NOT NULL DEFAULT '',
          chunk_text_hash TEXT NOT NULL DEFAULT '',
          surface_text TEXT NOT NULL,
          normalized_text TEXT NOT NULL,
          entity_type TEXT NOT NULL DEFAULT 'unknown',
          start_offset INTEGER NOT NULL DEFAULT 0,
          end_offset INTEGER NOT NULL DEFAULT 0,
          extractor TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 0.0,
          status TEXT NOT NULL DEFAULT 'candidate',
          resolution_status TEXT NOT NULL DEFAULT 'unresolved',
          resolved_node_id TEXT NOT NULL DEFAULT '',
          evidence_annotation_id TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS entity_resolution_candidates (
          id TEXT PRIMARY KEY,
          mention_id TEXT NOT NULL REFERENCES entity_mentions(id) ON DELETE CASCADE,
          node_id TEXT NOT NULL DEFAULT '',
          candidate_name TEXT NOT NULL DEFAULT '',
          score REAL NOT NULL DEFAULT 0.0,
          method TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'candidate',
          rationale_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS entity_resolution_decisions (
          id TEXT PRIMARY KEY,
          mention_id TEXT NOT NULL REFERENCES entity_mentions(id) ON DELETE CASCADE,
          candidate_id TEXT NOT NULL DEFAULT '',
          node_id TEXT NOT NULL DEFAULT '',
          decision TEXT NOT NULL,
          rationale TEXT NOT NULL DEFAULT '',
          reviewer TEXT NOT NULL DEFAULT 'praxis',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS evidence_annotations (
          id TEXT PRIMARY KEY,
          annotation_type TEXT NOT NULL,
          source_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
          resolved_entity_ids_json TEXT NOT NULL DEFAULT '[]',
          extracted_json TEXT NOT NULL DEFAULT '{}',
          confidence REAL NOT NULL DEFAULT 0.0,
          status TEXT NOT NULL DEFAULT 'candidate',
          extractor TEXT NOT NULL DEFAULT '',
          model_id TEXT NOT NULL DEFAULT '',
          governance_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS relation_candidates (
          id TEXT PRIMARY KEY,
          subject_entity_id TEXT NOT NULL DEFAULT '',
          predicate TEXT NOT NULL,
          object_entity_id TEXT NOT NULL DEFAULT '',
          object_value TEXT NOT NULL DEFAULT '',
          chunk_id TEXT NOT NULL DEFAULT '',
          evidence_annotation_id TEXT NOT NULL DEFAULT '',
          confidence REAL NOT NULL DEFAULT 0.0,
          status TEXT NOT NULL DEFAULT 'candidate',
          extractor TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_entity_mentions_chunk ON entity_mentions(chunk_id);
        CREATE INDEX IF NOT EXISTS idx_entity_mentions_normalized ON entity_mentions(normalized_text, status);
        CREATE INDEX IF NOT EXISTS idx_entity_mentions_resolved ON entity_mentions(resolved_node_id, resolution_status);
        CREATE INDEX IF NOT EXISTS idx_entity_candidates_mention ON entity_resolution_candidates(mention_id);
        CREATE INDEX IF NOT EXISTS idx_entity_candidates_node ON entity_resolution_candidates(node_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_annotations_status ON evidence_annotations(status);
        CREATE INDEX IF NOT EXISTS idx_relation_candidates_subject ON relation_candidates(subject_entity_id);
        CREATE INDEX IF NOT EXISTS idx_relation_candidates_object ON relation_candidates(object_entity_id);
        """
    )


def connect_entity_db(db_path: Path = DEFAULT_VECTOR_DB) -> sqlite3.Connection:
    connection = connect_vector(db_path)
    ensure_entity_schema(connection)
    return connection


@dataclass(frozen=True)
class GraphEntity:
    node_id: str
    name: str
    entity_type: str
    alias: str
    normalized_alias: str
    source: str
    confidence: str = "medium"


def load_graph_entities(kg_db: Path = DEFAULT_KG_DB) -> list[GraphEntity]:
    if not kg_db.exists():
        return []
    with sqlite3.connect(kg_db) as connection:
        connection.row_factory = sqlite3.Row
        status_clause = ", ".join("?" for _ in ACTIVE_NODE_STATUSES)
        rows = connection.execute(
            f"""
            SELECT id, type, name, confidence, name AS alias, 'name' AS source
            FROM nodes
            WHERE status IN ({status_clause})
            UNION ALL
            SELECT n.id, n.type, n.name, n.confidence, a.alias, 'alias' AS source
            FROM aliases a
            JOIN nodes n ON n.id = a.node_id
            WHERE n.status IN ({status_clause})
            """,
            (*ACTIVE_NODE_STATUSES, *ACTIVE_NODE_STATUSES),
        ).fetchall()
    entities: list[GraphEntity] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        alias = str(row["alias"] or "").strip()
        normalized = normalize_entity_text(alias)
        if len(normalized) < 3:
            continue
        key = (str(row["id"]), normalized)
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            GraphEntity(
                node_id=str(row["id"]),
                name=str(row["name"]),
                entity_type=str(row["type"]),
                alias=alias,
                normalized_alias=normalized,
                source=str(row["source"]),
                confidence=str(row["confidence"] or "medium"),
            )
        )
    return entities


def iter_chunks(connection: sqlite3.Connection, *, changed_only: bool = False, limit: int = 0) -> list[sqlite3.Row]:
    where = ""
    params: list[Any] = []
    if changed_only:
        where = """
        WHERE NOT EXISTS (
          SELECT 1
          FROM entity_mentions em
          WHERE em.chunk_id = sc.id
            AND em.chunk_text_hash = sc.text_hash
        )
        """
    if limit:
        params.append(limit)
        limit_clause = "LIMIT ?"
    else:
        limit_clause = ""
    return connection.execute(
        f"""
        SELECT sc.*, sd.path, sd.url
        FROM semantic_chunks sc
        JOIN semantic_documents sd ON sd.id = sc.document_id
        {where}
        ORDER BY sc.document_id, sc.chunk_index
        {limit_clause}
        """,
        params,
    ).fetchall()


def mention_payload(
    *,
    chunk: sqlite3.Row,
    surface_text: str,
    entity_type: str,
    start_offset: int,
    end_offset: int,
    extractor: str,
    confidence: float,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_entity_text(surface_text)
    mention_id = stable_id(
        "mention",
        [
            str(chunk["id"]),
            normalized,
            str(start_offset),
            str(end_offset),
            entity_type,
            extractor,
        ],
    )
    return {
        "id": mention_id,
        "chunk_id": str(chunk["id"]),
        "document_id": str(chunk["document_id"]),
        "chunk_text_hash": str(chunk["text_hash"]),
        "surface_text": surface_text,
        "normalized_text": normalized,
        "entity_type": entity_type,
        "start_offset": int(start_offset),
        "end_offset": int(end_offset),
        "extractor": extractor,
        "confidence": float(confidence),
        "status": "candidate",
        "resolution_status": "unresolved",
        "resolved_node_id": "",
        "evidence_annotation_id": "",
        "metadata_json": json_dumps(metadata or {}),
    }


def upsert_mention(connection: sqlite3.Connection, payload: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO entity_mentions(
          id, chunk_id, document_id, chunk_text_hash, surface_text, normalized_text, entity_type,
          start_offset, end_offset, extractor, confidence, status, resolution_status,
          resolved_node_id, evidence_annotation_id, metadata_json
        )
        VALUES (
          :id, :chunk_id, :document_id, :chunk_text_hash, :surface_text, :normalized_text, :entity_type,
          :start_offset, :end_offset, :extractor, :confidence, :status, :resolution_status,
          :resolved_node_id, :evidence_annotation_id, :metadata_json
        )
        ON CONFLICT(id) DO UPDATE SET
          surface_text=excluded.surface_text,
          normalized_text=excluded.normalized_text,
          entity_type=excluded.entity_type,
          confidence=excluded.confidence,
          status=excluded.status,
          metadata_json=excluded.metadata_json,
          updated_at=CURRENT_TIMESTAMP
        """,
        payload,
    )


def upsert_candidate(
    connection: sqlite3.Connection,
    *,
    mention_id: str,
    node_id: str,
    candidate_name: str,
    score: float,
    method: str,
    status: str,
    rationale: dict[str, Any],
) -> str:
    candidate_id = stable_id("entity-candidate", [mention_id, node_id, method])
    connection.execute(
        """
        INSERT INTO entity_resolution_candidates(
          id, mention_id, node_id, candidate_name, score, method, status, rationale_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          candidate_name=excluded.candidate_name,
          score=excluded.score,
          method=excluded.method,
          status=excluded.status,
          rationale_json=excluded.rationale_json,
          updated_at=CURRENT_TIMESTAMP
        """,
        (candidate_id, mention_id, node_id, candidate_name, score, method, status, json_dumps(rationale)),
    )
    return candidate_id


def record_resolution_decision(
    connection: sqlite3.Connection,
    *,
    mention_id: str,
    candidate_id: str,
    node_id: str,
    decision: str,
    rationale: str,
    reviewer: str = "praxis",
) -> str:
    decision_id = stable_id("entity-decision", [mention_id, candidate_id, node_id, decision, rationale])
    connection.execute(
        """
        INSERT OR IGNORE INTO entity_resolution_decisions(
          id, mention_id, candidate_id, node_id, decision, rationale, reviewer
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (decision_id, mention_id, candidate_id, node_id, decision, rationale, reviewer),
    )
    return decision_id


def upsert_evidence_annotation(
    connection: sqlite3.Connection,
    *,
    annotation_type: str,
    chunk_ids: list[str],
    entity_ids: list[str],
    extracted: dict[str, Any],
    confidence: float,
    status: str,
    extractor: str,
    model_id: str = "",
    governance: dict[str, Any] | None = None,
) -> str:
    annotation_id = stable_id(
        "ann",
        [
            annotation_type,
            ",".join(sorted(chunk_ids)),
            ",".join(sorted(entity_ids)),
            sha256_text(json_dumps(extracted))[:16],
        ],
    )
    connection.execute(
        """
        INSERT INTO evidence_annotations(
          id, annotation_type, source_chunk_ids_json, resolved_entity_ids_json,
          extracted_json, confidence, status, extractor, model_id, governance_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          extracted_json=excluded.extracted_json,
          confidence=excluded.confidence,
          status=excluded.status,
          extractor=excluded.extractor,
          model_id=excluded.model_id,
          governance_json=excluded.governance_json,
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            annotation_id,
            annotation_type,
            json_dumps(chunk_ids),
            json_dumps(entity_ids),
            json_dumps(extracted),
            confidence,
            status,
            extractor,
            model_id,
            json_dumps(governance or {}),
        ),
    )
    return annotation_id


def accepted_mentions_for_node(connection: sqlite3.Connection, node_id: str, *, limit: int = 10) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT em.*, sc.title, sc.section, sc.text, sd.path, sd.url
        FROM entity_mentions em
        JOIN semantic_chunks sc ON sc.id = em.chunk_id
        JOIN semantic_documents sd ON sd.id = sc.document_id
        WHERE em.resolved_node_id = ?
          AND em.resolution_status = 'accepted'
        ORDER BY em.updated_at DESC
        LIMIT ?
        """,
        (node_id, limit),
    ).fetchall()


def annotation_by_id(connection: sqlite3.Connection, annotation_id: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM evidence_annotations WHERE id = ?", (annotation_id,)).fetchone()


def annotation_conflict_count(payload: dict[str, Any]) -> int:
    governance = payload.get("governance")
    if isinstance(governance, dict):
        conflicts = governance.get("conflict_records") or governance.get("conflicts") or []
        return len(conflicts) if isinstance(conflicts, list) else 0
    return 0
