"""Audit and rollback helpers for SkillGraph mutations."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from init_skill_graph import upsert_edge, upsert_evidence, upsert_node
from research_common import slug, utc_now


LIVE_STATUSES = ("active", "provisional")


def _json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


class RollbackConflictError(RuntimeError):
    """Raised when rollback would overwrite a later graph change."""

    def __init__(self, conflicts: list[str]) -> None:
        self.conflicts = conflicts
        super().__init__("Rollback conflict: " + "; ".join(conflicts))


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_audit_schema(connection: sqlite3.Connection) -> None:
    """Create migration-safe audit tables and keep edge_view status-aware."""
    connection.execute("PRAGMA foreign_keys = ON")
    _ensure_column(connection, "evidence", "status", "TEXT NOT NULL DEFAULT 'active'")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS graph_change_sets (
          id TEXT PRIMARY KEY,
          action TEXT NOT NULL,
          mode TEXT NOT NULL DEFAULT 'auto',
          source_id TEXT NOT NULL DEFAULT '',
          capture_id TEXT NOT NULL DEFAULT '',
          proposal_id TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL DEFAULT '',
          summary TEXT NOT NULL DEFAULT '',
          actor TEXT NOT NULL DEFAULT 'praxis',
          status TEXT NOT NULL DEFAULT 'applied',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          reverted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS graph_change_items (
          id TEXT PRIMARY KEY,
          change_set_id TEXT NOT NULL REFERENCES graph_change_sets(id) ON DELETE CASCADE,
          object_type TEXT NOT NULL,
          object_id TEXT NOT NULL,
          operation TEXT NOT NULL,
          before_json TEXT,
          after_json TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_graph_change_sets_status ON graph_change_sets(status);
        CREATE INDEX IF NOT EXISTS idx_graph_change_sets_capture ON graph_change_sets(capture_id);
        CREATE INDEX IF NOT EXISTS idx_graph_change_items_change_set ON graph_change_items(change_set_id);
        CREATE INDEX IF NOT EXISTS idx_graph_change_items_object ON graph_change_items(object_type, object_id);

        DROP VIEW IF EXISTS edge_view;
        CREATE VIEW edge_view AS
        SELECT
          e.id,
          e.relation,
          e.confidence,
          e.weight,
          e.summary,
          e.status,
          e.status AS edge_status,
          e.source_id,
          s.name AS source_name,
          s.type AS source_type,
          s.status AS source_status,
          e.target_id,
          t.name AS target_name,
          t.type AS target_type,
          t.status AS target_status,
          e.evidence_id,
          ev.title AS evidence_title,
          ev.source_path AS evidence_source_path,
          ev.url AS evidence_url,
          ev.locator AS evidence_locator,
          ev.status AS evidence_status
        FROM edges e
        JOIN nodes s ON s.id = e.source_id
        JOIN nodes t ON t.id = e.target_id
        LEFT JOIN evidence ev ON ev.id = e.evidence_id;
        """
    )


def _node_payload(connection: sqlite3.Connection, node_id: str) -> dict[str, Any] | None:
    row = _row_dict(connection.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone())
    if not row:
        return None
    aliases = [
        item["alias"]
        for item in connection.execute("SELECT alias FROM aliases WHERE node_id = ? ORDER BY alias", (node_id,)).fetchall()
    ]
    tags = [
        item["name"]
        for item in connection.execute(
            """
            SELECT t.name
            FROM node_tags nt
            JOIN tags t ON t.id = nt.tag_id
            WHERE nt.node_id = ?
            ORDER BY t.name
            """,
            (node_id,),
        ).fetchall()
    ]
    row["aliases"] = aliases
    row["tags"] = tags
    return row


def fetch_graph_object(connection: sqlite3.Connection, object_type: str, object_id: str) -> dict[str, Any] | None:
    if object_type == "node":
        return _node_payload(connection, object_id)
    if object_type == "edge":
        return _row_dict(connection.execute("SELECT * FROM edges WHERE id = ?", (object_id,)).fetchone())
    if object_type == "evidence":
        return _row_dict(connection.execute("SELECT * FROM evidence WHERE id = ?", (object_id,)).fetchone())
    raise ValueError(f"Unsupported graph object type: {object_type}")


def object_id_for(object_type: str, payload: dict[str, Any]) -> str:
    if object_type in {"node", "evidence"}:
        return payload["id"]
    if object_type == "edge":
        from init_skill_graph import edge_id

        return payload.get("id") or edge_id(
            payload["source_id"],
            payload["relation"],
            payload["target_id"],
            payload.get("evidence_id") or None,
        )
    raise ValueError(f"Unsupported graph object type: {object_type}")


def create_change_set(
    connection: sqlite3.Connection,
    *,
    action: str,
    mode: str,
    title: str,
    summary: str = "",
    source_id: str = "",
    capture_id: str = "",
    proposal_id: str = "",
    actor: str = "praxis",
    metadata: dict[str, Any] | None = None,
) -> str:
    ensure_audit_schema(connection)
    now = utc_now()
    raw = "|".join([action, mode, source_id, capture_id, proposal_id, title, now])
    change_set_id = f"chg:{slug(title or action)}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"
    connection.execute(
        """
        INSERT INTO graph_change_sets(
          id, action, mode, source_id, capture_id, proposal_id, title, summary,
          actor, status, metadata_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'applied', ?, ?)
        """,
        (
            change_set_id,
            action,
            mode,
            source_id,
            capture_id,
            proposal_id,
            title,
            summary,
            actor,
            json.dumps(metadata or {}, sort_keys=True),
            now,
        ),
    )
    return change_set_id


def log_change_item(
    connection: sqlite3.Connection,
    *,
    change_set_id: str,
    object_type: str,
    object_id: str,
    operation: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    raw = "|".join([change_set_id, object_type, object_id, operation, _json(before), _json(after)])
    item_id = f"chgitem:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"
    connection.execute(
        """
        INSERT OR IGNORE INTO graph_change_items(
          id, change_set_id, object_type, object_id, operation, before_json, after_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id,
            change_set_id,
            object_type,
            object_id,
            operation,
            json.dumps(before, sort_keys=True) if before is not None else None,
            json.dumps(after, sort_keys=True) if after is not None else None,
        ),
    )


def audited_upsert(
    connection: sqlite3.Connection,
    *,
    change_set_id: str,
    object_type: str,
    payload: dict[str, Any],
    upsert: Callable[[sqlite3.Connection, dict[str, Any]], None],
) -> str:
    object_id = object_id_for(object_type, payload)
    if object_type == "edge" and "id" not in payload:
        payload = {**payload, "id": object_id}
    before = fetch_graph_object(connection, object_type, object_id)
    upsert(connection, payload)
    after = fetch_graph_object(connection, object_type, object_id)
    operation = "create" if before is None else "update"
    log_change_item(
        connection,
        change_set_id=change_set_id,
        object_type=object_type,
        object_id=object_id,
        operation=operation,
        before=before,
        after=after,
    )
    return operation


def restore_graph_object(connection: sqlite3.Connection, object_type: str, payload: dict[str, Any]) -> None:
    if object_type == "node":
        upsert_node(connection, payload)
    elif object_type == "edge":
        upsert_edge(connection, payload)
    elif object_type == "evidence":
        upsert_evidence(connection, payload)
    else:
        raise ValueError(f"Unsupported graph object type: {object_type}")


def mark_graph_object_status(connection: sqlite3.Connection, object_type: str, object_id: str, status: str) -> None:
    if object_type == "node":
        connection.execute("UPDATE nodes SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, object_id))
    elif object_type == "edge":
        connection.execute("UPDATE edges SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, object_id))
    elif object_type == "evidence":
        connection.execute("UPDATE evidence SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, object_id))
    else:
        raise ValueError(f"Unsupported graph object type: {object_type}")


def change_graph_object_status(
    connection: sqlite3.Connection,
    *,
    object_type: str,
    object_id: str,
    status: str,
    change_set_id: str,
) -> bool:
    before = fetch_graph_object(connection, object_type, object_id)
    if before is None:
        raise ValueError(f"{object_type} not found: {object_id}")
    mark_graph_object_status(connection, object_type, object_id, status)
    after = fetch_graph_object(connection, object_type, object_id)
    log_change_item(
        connection,
        change_set_id=change_set_id,
        object_type=object_type,
        object_id=object_id,
        operation=f"status:{status}",
        before=before,
        after=after,
    )
    return before.get("status") != status


def change_change_set_object_statuses(
    connection: sqlite3.Connection,
    source_change_set_id: str,
    *,
    status: str,
    action: str,
    actor: str = "praxis",
    include_evidence: bool = True,
) -> int:
    ensure_audit_schema(connection)
    source_change_set = connection.execute("SELECT * FROM graph_change_sets WHERE id = ?", (source_change_set_id,)).fetchone()
    if not source_change_set:
        raise ValueError(f"Change set not found: {source_change_set_id}")

    rows = connection.execute(
        """
        SELECT DISTINCT object_type, object_id
        FROM graph_change_items
        WHERE change_set_id = ?
        ORDER BY object_type, object_id
        """,
        (source_change_set_id,),
    ).fetchall()

    targets: list[tuple[str, str]] = []
    missing: list[str] = []
    for row in rows:
        object_type = row["object_type"]
        if object_type == "evidence" and not include_evidence:
            continue
        object_id = row["object_id"]
        current = fetch_graph_object(connection, object_type, object_id)
        if current is None:
            missing.append(f"{object_type} `{object_id}`")
            continue
        if current.get("status") != status:
            targets.append((object_type, object_id))
    if missing:
        raise ValueError("Cannot change status for missing graph objects: " + ", ".join(missing))
    if not targets:
        return 0

    title = f"{action.title()} {source_change_set_id}"
    change_set_id = create_change_set(
        connection,
        action=action,
        mode="manual",
        title=title,
        summary=f"Set graph objects from {source_change_set_id} to {status}.",
        source_id=source_change_set["source_id"],
        capture_id=source_change_set["capture_id"],
        proposal_id=source_change_set["proposal_id"],
        actor=actor,
        metadata={"target_change_set": source_change_set_id, "status": status},
    )

    changed = 0
    for object_type, object_id in targets:
        if change_graph_object_status(
            connection,
            object_type=object_type,
            object_id=object_id,
            status=status,
            change_set_id=change_set_id,
        ):
            changed += 1
    return changed


def _loads(value: str | None) -> dict[str, Any] | None:
    return json.loads(value) if value else None


def _graph_object_matches_expected(current: dict[str, Any] | None, expected: dict[str, Any] | None) -> bool:
    return _json(current) == _json(expected)


def rollback_conflicts(connection: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[str]:
    conflicts = []
    for row in rows:
        object_type = row["object_type"]
        object_id = row["object_id"]
        expected_after = _loads(row["after_json"])
        current = fetch_graph_object(connection, object_type, object_id)
        if not _graph_object_matches_expected(current, expected_after):
            conflicts.append(f"{object_type} `{object_id}` changed after the audited change set")
    return conflicts


def rollback_change_set(connection: sqlite3.Connection, change_set_id: str, *, actor: str = "praxis", force: bool = False) -> int:
    ensure_audit_schema(connection)
    change_set = connection.execute("SELECT * FROM graph_change_sets WHERE id = ?", (change_set_id,)).fetchone()
    if not change_set:
        raise ValueError(f"Change set not found: {change_set_id}")
    if change_set["status"] == "reverted":
        return 0

    rows = connection.execute(
        """
        SELECT *
        FROM graph_change_items
        WHERE change_set_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (change_set_id,),
    ).fetchall()
    conflicts = rollback_conflicts(connection, rows)
    if conflicts and not force:
        raise RollbackConflictError(conflicts)

    rollback_id = create_change_set(
        connection,
        action="rollback",
        mode="manual",
        title=f"Rollback {change_set_id}",
        summary=f"Rollback of {change_set['title']}",
        source_id=change_set["source_id"],
        capture_id=change_set["capture_id"],
        proposal_id=change_set["proposal_id"],
        actor=actor,
        metadata={"reverts": change_set_id},
    )

    reverted = 0
    for row in rows:
        object_type = row["object_type"]
        object_id = row["object_id"]
        before = _loads(row["before_json"])
        current = fetch_graph_object(connection, object_type, object_id)
        if before is None:
            mark_graph_object_status(connection, object_type, object_id, "reverted")
        else:
            restore_graph_object(connection, object_type, before)
        after = fetch_graph_object(connection, object_type, object_id)
        log_change_item(
            connection,
            change_set_id=rollback_id,
            object_type=object_type,
            object_id=object_id,
            operation="rollback",
            before=current,
            after=after,
        )
        reverted += 1

    now = utc_now()
    connection.execute(
        "UPDATE graph_change_sets SET status = 'reverted', reverted_at = ? WHERE id = ?",
        (now, change_set_id),
    )
    return reverted


def live_status_clause(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"{prefix}status IN ('active', 'provisional')"
