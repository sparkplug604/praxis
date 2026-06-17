"""Query and compare accepted relationship evidence."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from praxis.entities.storage import json_dumps, normalize_entity_text, stable_id

from .storage import connect_relationship_evidence_db, edge_from_row, parsed_annotation


def _like(value: str) -> str:
    return f"%{value.lower()}%"


def _edge_payload(row, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = asdict(edge_from_row(row))
    for key in ("chunk_title", "chunk_section", "document_path", "document_url"):
        if key in row.keys():
            payload[key] = str(row[key] or "")
    if evidence is not None:
        payload["evidence"] = evidence
    return payload


def find_relationships(
    *,
    vector_db: Path,
    subject: str = "",
    predicate: str = "",
    object_value: str = "",
    query: str = "",
    status: str = "accepted",
    limit: int = 20,
    include_evidence: bool = True,
) -> list[dict[str, Any]]:
    clauses = ["age.status = ?"]
    params: list[Any] = [status]
    if subject:
        clauses.append("(lower(age.subject_text) LIKE ? OR lower(age.subject_entity_id) LIKE ?)")
        params.extend([_like(subject), _like(subject)])
    if predicate:
        clauses.append("age.predicate = ?")
        params.append(predicate)
    if object_value:
        clauses.append("(lower(age.object_value) LIKE ? OR lower(age.object_entity_id) LIKE ?)")
        params.extend([_like(object_value), _like(object_value)])
    if query:
        normalized = normalize_entity_text(query)
        for token in [token for token in normalized.split() if len(token) >= 3][:6]:
            clauses.append("(lower(age.subject_text) LIKE ? OR lower(age.object_value) LIKE ? OR lower(age.predicate) LIKE ?)")
            params.extend([_like(token), _like(token), _like(token)])
    params.append(limit)
    with connect_relationship_evidence_db(vector_db) as connection:
        rows = connection.execute(
            f"""
            SELECT age.*, sc.title AS chunk_title, sc.section AS chunk_section, sd.path AS document_path, sd.url AS document_url
            FROM accepted_graph_edges age
            LEFT JOIN semantic_chunks sc ON sc.id = age.chunk_id
            LEFT JOIN semantic_documents sd ON sd.id = sc.document_id
            WHERE {' AND '.join(clauses)}
            ORDER BY age.confidence DESC, age.updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            evidence = parsed_annotation(connection, str(row["evidence_annotation_id"])) if include_evidence else None
            results.append(_edge_payload(row, evidence=evidence))
    return results


def compare_entity_relationships(
    *,
    vector_db: Path,
    left: str,
    right: str,
    limit: int = 50,
) -> dict[str, Any]:
    left_edges = find_relationships(vector_db=vector_db, subject=left, limit=limit, include_evidence=True)
    right_edges = find_relationships(vector_db=vector_db, subject=right, limit=limit, include_evidence=True)
    left_pairs = {(edge["predicate"], normalize_entity_text(edge["object_value"])): edge for edge in left_edges}
    right_pairs = {(edge["predicate"], normalize_entity_text(edge["object_value"])): edge for edge in right_edges}
    shared_keys = sorted(set(left_pairs) & set(right_pairs))
    shared = [
        {
            "predicate": predicate,
            "object_value": left_pairs[(predicate, object_key)]["object_value"],
            "left_edge_id": left_pairs[(predicate, object_key)]["id"],
            "right_edge_id": right_pairs[(predicate, object_key)]["id"],
        }
        for predicate, object_key in shared_keys
    ]
    trace = {
        "left": left,
        "right": right,
        "left_edge_count": len(left_edges),
        "right_edge_count": len(right_edges),
        "shared_count": len(shared),
    }
    with connect_relationship_evidence_db(vector_db) as connection:
        connection.execute(
            """
            INSERT INTO relationship_evidence_query_traces(id, query, planner_json, result_count, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                stable_id("graph-query", ["compare", left, right, json_dumps(trace)]),
                f"compare:{left}:{right}",
                json_dumps({"operation": "compare_entity_relationships", "left": left, "right": right}),
                len(shared),
                json_dumps(trace),
            ),
        )
    return {
        "left": left,
        "right": right,
        "left_edges": left_edges,
        "right_edges": right_edges,
        "shared_relationships": shared,
    }
