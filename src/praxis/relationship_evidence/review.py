"""Review helpers for relationship evidence candidates and conflicts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from praxis.entities.storage import json_dumps

from .storage import connect_relationship_evidence_db


def _review_payload(row) -> dict[str, Any]:
    payload = dict(row)
    try:
        payload["metadata"] = json.loads(payload.get("metadata_json") or "{}")
    except json.JSONDecodeError:
        payload["metadata"] = {}
    return payload


def list_review_items(*, vector_db: Path, status: str = "open", limit: int = 25) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with connect_relationship_evidence_db(vector_db) as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM relationship_evidence_review_items
            {where}
            ORDER BY created_at DESC, id
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_review_payload(row) for row in rows]


def get_review_item(*, vector_db: Path, review_id: str) -> dict[str, Any] | None:
    with connect_relationship_evidence_db(vector_db) as connection:
        row = connection.execute(
            "SELECT * FROM relationship_evidence_review_items WHERE id = ?",
            (review_id,),
        ).fetchone()
    return _review_payload(row) if row else None


def resolve_review_item(
    *,
    vector_db: Path,
    review_id: str,
    status: str,
    resolution: str = "",
    notes: str = "",
) -> bool:
    item = get_review_item(vector_db=vector_db, review_id=review_id)
    if item is None:
        return False
    metadata = dict(item.get("metadata") or {})
    if resolution:
        metadata["resolution"] = resolution
    if notes:
        metadata["notes"] = notes
    with connect_relationship_evidence_db(vector_db) as connection:
        connection.execute(
            """
            UPDATE relationship_evidence_review_items
            SET status = ?,
                metadata_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, json_dumps(metadata), review_id),
        )
    return True
