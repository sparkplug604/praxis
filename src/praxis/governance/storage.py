"""Storage and hash-chain receipts for Core governance events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from praxis.paths import governance_dir as workspace_governance_dir

from .models import GovernanceEvent, GovernanceReceipt


def governance_dir(root: Path) -> Path:
    return workspace_governance_dir(root)


def governance_db_path(root: Path) -> Path:
    return governance_dir(root) / "governance.sqlite"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def connect(root: Path) -> sqlite3.Connection:
    governance_dir(root).mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(governance_db_path(root))
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS governance_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            decision TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL DEFAULT 'praxis',
            payload_hash TEXT NOT NULL,
            previous_hash TEXT NOT NULL DEFAULT '',
            receipt_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_governance_events_type ON governance_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_governance_events_created ON governance_events(created_at);
        """
    )


def init_governance(root: Path) -> Path:
    with connect(root):
        pass
    return governance_db_path(root)


def latest_receipt_hash(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT receipt_hash FROM governance_events ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    return str(row["receipt_hash"]) if row else ""


def record_event(root: Path, event: GovernanceEvent) -> GovernanceReceipt:
    created_at = utc_now()
    payload = event.to_dict()
    payload_hash = stable_hash(payload)
    with connect(root) as connection:
        previous_hash = latest_receipt_hash(connection)
        receipt_hash = stable_hash(
            {
                "event_type": event.event_type,
                "decision": event.decision,
                "actor": event.actor,
                "payload_hash": payload_hash,
                "previous_hash": previous_hash,
                "created_at": created_at,
            }
        )
        event_id = f"gov:{event.event_type}:{receipt_hash[:16]}"
        connection.execute(
            """
            INSERT INTO governance_events(
                event_id, event_type, decision, actor, payload_hash, previous_hash,
                receipt_hash, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event.event_type,
                event.decision,
                event.actor,
                payload_hash,
                previous_hash,
                receipt_hash,
                canonical_json(payload),
                created_at,
            ),
        )
    return GovernanceReceipt(
        event_id=event_id,
        event_type=event.event_type,
        payload_hash=payload_hash,
        previous_hash=previous_hash,
        receipt_hash=receipt_hash,
        created_at=created_at,
        actor=event.actor,
    )


def list_events(root: Path, *, limit: int = 25) -> list[dict[str, Any]]:
    with connect(root) as connection:
        rows = connection.execute(
            """
            SELECT event_id, event_type, decision, actor, payload_hash, previous_hash, receipt_hash, created_at
            FROM governance_events
            ORDER BY rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def show_event(root: Path, event_id: str) -> dict[str, Any] | None:
    with connect(root) as connection:
        row = connection.execute("SELECT * FROM governance_events WHERE event_id = ?", (event_id,)).fetchone()
    if row is None:
        return None
    payload = dict(row)
    payload["payload"] = json.loads(payload.pop("payload_json"))
    return payload


def verify_receipts(root: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    with connect(root) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM governance_events
            ORDER BY rowid ASC
            """
        ).fetchall()
    previous_hash = ""
    for row in rows:
        payload = json.loads(row["payload_json"])
        payload_hash = stable_hash(payload)
        if payload_hash != row["payload_hash"]:
            errors.append(f"{row['event_id']}: payload hash mismatch")
        if row["previous_hash"] != previous_hash:
            errors.append(f"{row['event_id']}: previous hash mismatch")
        expected_receipt = stable_hash(
            {
                "event_type": row["event_type"],
                "decision": row["decision"],
                "actor": row["actor"],
                "payload_hash": row["payload_hash"],
                "previous_hash": row["previous_hash"],
                "created_at": row["created_at"],
            }
        )
        if expected_receipt != row["receipt_hash"]:
            errors.append(f"{row['event_id']}: receipt hash mismatch")
        previous_hash = row["receipt_hash"]
    return not errors, errors
