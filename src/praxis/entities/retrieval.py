"""Entity-aware retrieval helpers for Praxis search."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .storage import connect_entity_db, normalize_entity_text


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def entity_hints_for_query(vector_db: Path, kg_db: Path, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    normalized = normalize_entity_text(query)
    tokens = [token for token in normalized.split() if len(token) >= 3]
    hints: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    if not tokens:
        return hints
    with connect_entity_db(vector_db) as connection:
        clauses = ["em.normalized_text = ?"]
        params: list[Any] = [normalized]
        for token in tokens[:8]:
            clauses.append("em.normalized_text LIKE ?")
            params.append(f"%{token}%")
        params.append(limit * 4)
        rows = connection.execute(
            f"""
            SELECT em.resolved_node_id, em.surface_text, em.normalized_text, em.confidence,
                   COUNT(*) AS mention_count,
                   MAX(em.evidence_annotation_id) AS evidence_annotation_id
            FROM entity_mentions em
            WHERE em.resolution_status = 'accepted'
              AND em.resolved_node_id != ''
              AND ({' OR '.join(clauses)})
            GROUP BY em.resolved_node_id, em.surface_text, em.normalized_text
            ORDER BY mention_count DESC, em.confidence DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        for row in rows:
            node_id = str(row["resolved_node_id"])
            if node_id in seen_nodes:
                continue
            seen_nodes.add(node_id)
            hints.append(
                {
                    "node_id": node_id,
                    "surface_text": str(row["surface_text"]),
                    "normalized_text": str(row["normalized_text"]),
                    "score": min(1.0, 0.65 + (0.05 * int(row["mention_count"] or 0))),
                    "source": "entity_mentions",
                    "evidence_annotation_id": str(row["evidence_annotation_id"] or ""),
                }
            )
    if kg_db.exists():
        with sqlite3.connect(kg_db) as kg:
            kg.row_factory = sqlite3.Row
            clauses = ["lower(n.name) LIKE ?"]
            params = [f"%{query.lower()}%"]
            for token in tokens[:8]:
                clauses.extend(["lower(n.name) LIKE ?", "lower(a.alias) LIKE ?"])
                params.extend([f"%{token}%", f"%{token}%"])
            params.append(limit * 2)
            rows = kg.execute(
                f"""
                SELECT DISTINCT n.id, n.name, n.type
                FROM nodes n
                LEFT JOIN aliases a ON a.node_id = n.id
                WHERE n.status IN ('active', 'provisional')
                  AND ({' OR '.join(clauses)})
                LIMIT ?
                """,
                params,
            ).fetchall()
            for row in rows:
                node_id = str(row["id"])
                if node_id in seen_nodes:
                    continue
                seen_nodes.add(node_id)
                hints.append(
                    {
                        "node_id": node_id,
                        "surface_text": str(row["name"]),
                        "normalized_text": normalize_entity_text(str(row["name"])),
                        "score": 0.55,
                        "source": "skillgraph",
                        "evidence_annotation_id": "",
                    }
                )
                if len(hints) >= limit:
                    break
    return hints[:limit]


def entity_scores_for_chunks(vector_db: Path, chunk_ids: list[str], hints: list[dict[str, Any]]) -> dict[str, float]:
    if not chunk_ids or not hints:
        return {}
    hint_nodes = {str(hint["node_id"]) for hint in hints if hint.get("node_id")}
    if not hint_nodes:
        return {}
    placeholders_chunks = ", ".join("?" for _ in chunk_ids)
    placeholders_nodes = ", ".join("?" for _ in hint_nodes)
    params = [*chunk_ids, *sorted(hint_nodes)]
    scores: dict[str, float] = {}
    with connect_entity_db(vector_db) as connection:
        rows = connection.execute(
            f"""
            SELECT chunk_id, resolved_node_id, COUNT(*) AS count, MAX(confidence) AS confidence
            FROM entity_mentions
            WHERE chunk_id IN ({placeholders_chunks})
              AND resolved_node_id IN ({placeholders_nodes})
              AND resolution_status = 'accepted'
            GROUP BY chunk_id, resolved_node_id
            """,
            params,
        ).fetchall()
    for row in rows:
        chunk_id = str(row["chunk_id"])
        score = min(1.0, 0.55 + (0.15 * int(row["count"] or 0)) + (0.20 * float(row["confidence"] or 0.0)))
        scores[chunk_id] = max(scores.get(chunk_id, 0.0), score)
    return scores


def accepted_entity_links_for_chunk(vector_db: Path, chunk_id: str, *, limit: int = 8) -> list[dict[str, Any]]:
    with connect_entity_db(vector_db) as connection:
        rows = connection.execute(
            """
            SELECT resolved_node_id, surface_text, entity_type, confidence, evidence_annotation_id
            FROM entity_mentions
            WHERE chunk_id = ?
              AND resolution_status = 'accepted'
              AND resolved_node_id != ''
            ORDER BY confidence DESC, surface_text
            LIMIT ?
            """,
            (chunk_id, limit),
        ).fetchall()
    return _rows_to_dicts(rows)


def annotation_payload(vector_db: Path, annotation_id: str) -> dict[str, Any] | None:
    with connect_entity_db(vector_db) as connection:
        row = connection.execute("SELECT * FROM evidence_annotations WHERE id = ?", (annotation_id,)).fetchone()
    if row is None:
        return None
    payload = dict(row)
    for key in ("source_chunk_ids_json", "resolved_entity_ids_json"):
        try:
            payload[key.removesuffix("_json")] = json.loads(payload[key] or "[]")
        except json.JSONDecodeError:
            payload[key.removesuffix("_json")] = []
    for key in ("extracted_json", "governance_json"):
        try:
            payload[key.removesuffix("_json")] = json.loads(payload[key] or "{}")
        except json.JSONDecodeError:
            payload[key.removesuffix("_json")] = {}
    return payload
