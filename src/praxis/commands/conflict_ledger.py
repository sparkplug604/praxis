"""Conflict, contradiction, and dedupe helpers for the Praxis SkillGraph."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from research_common import slug, utc_now


UNRESOLVED_STATUSES = ("open", "acknowledged")
LIVE_STATUSES = ("active", "provisional")
DEDUP_TYPES = ("duplicate_source", "duplicate_content", "duplicate_entity", "duplicate_claim")
CLAIM_NODE_TYPES = {"claim", "practice", "pattern", "failure_mode", "policy", "rule", "concept"}
NEGATIVE_TERMS = {
    "avoid",
    "forbid",
    "forbidden",
    "never",
    "not",
    "reject",
    "remove",
    "disable",
    "deny",
    "deprecated",
    "deprecate",
}
POSITIVE_TERMS = {
    "use",
    "uses",
    "using",
    "prefer",
    "preferred",
    "recommend",
    "recommended",
    "require",
    "requires",
    "required",
    "enable",
    "enabled",
    "allow",
    "allowed",
    "support",
    "supports",
}
SUBJECT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "by",
    "can",
    "for",
    "from",
    "if",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "should",
    "that",
    "the",
    "then",
    "this",
    "to",
    "with",
    *NEGATIVE_TERMS,
    *POSITIVE_TERMS,
}


def ensure_conflict_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS claim_records (
          id TEXT PRIMARY KEY,
          node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
          claim_key TEXT NOT NULL,
          claim_text TEXT NOT NULL,
          normalized_text TEXT NOT NULL,
          subject_key TEXT NOT NULL,
          polarity TEXT NOT NULL DEFAULT 'neutral',
          source_ref TEXT NOT NULL DEFAULT '',
          confidence TEXT NOT NULL DEFAULT 'medium',
          status TEXT NOT NULL DEFAULT 'active',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS conflict_records (
          id TEXT PRIMARY KEY,
          conflict_type TEXT NOT NULL,
          severity TEXT NOT NULL DEFAULT 'medium',
          status TEXT NOT NULL DEFAULT 'open',
          summary TEXT NOT NULL,
          detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          resolved_at TEXT,
          resolution TEXT NOT NULL DEFAULT '',
          resolver_notes TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS conflict_items (
          conflict_id TEXT NOT NULL REFERENCES conflict_records(id) ON DELETE CASCADE,
          object_type TEXT NOT NULL,
          object_id TEXT NOT NULL,
          role TEXT NOT NULL,
          evidence_id TEXT NOT NULL DEFAULT '',
          rationale_json TEXT NOT NULL DEFAULT '{}',
          PRIMARY KEY (conflict_id, object_type, object_id, role)
        );

        CREATE INDEX IF NOT EXISTS idx_claim_records_node ON claim_records(node_id);
        CREATE INDEX IF NOT EXISTS idx_claim_records_subject ON claim_records(subject_key, polarity, status);
        CREATE INDEX IF NOT EXISTS idx_conflict_records_status ON conflict_records(status);
        CREATE INDEX IF NOT EXISTS idx_conflict_records_type ON conflict_records(conflict_type);
        CREATE INDEX IF NOT EXISTS idx_conflict_items_object ON conflict_items(object_type, object_id);
        """
    )


def has_conflict_schema(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'conflict_records'
        """
    ).fetchone()
    return row is not None


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_text(text: str) -> str:
    return normalize_space(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()))


def normalize_entity_name(text: str) -> str:
    normalized = normalize_text(text)
    tokens = [
        token
        for token in normalized.split()
        if token not in {"dr", "mr", "mrs", "ms", "miss", "prof", "the", "a", "an", "inc", "llc", "ltd"}
    ]
    return " ".join(tokens)


def canonical_url(value: str) -> str:
    if not value:
        return ""
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return normalize_text(value)
    if not parts.scheme or not parts.netloc:
        return normalize_text(value)
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def stable_id(prefix: str, parts: Iterable[str]) -> str:
    raw = "|".join(parts)
    return f"{prefix}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def insert_conflict(
    connection: sqlite3.Connection,
    *,
    conflict_type: str,
    severity: str,
    summary: str,
    items: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> str:
    ensure_conflict_schema(connection)
    item_key = [
        f"{item['object_type']}:{item['object_id']}:{item.get('role', '')}"
        for item in sorted(items, key=lambda item: (item["object_type"], item["object_id"], item.get("role", "")))
    ]
    conflict_id = stable_id(f"conflict:{conflict_type}", item_key)
    now = utc_now()
    connection.execute(
        """
        INSERT INTO conflict_records(
          id, conflict_type, severity, status, summary, detected_at, metadata_json
        )
        VALUES (?, ?, ?, 'open', ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          severity=excluded.severity,
          summary=excluded.summary,
          metadata_json=excluded.metadata_json
        WHERE conflict_records.status IN ('open', 'acknowledged')
        """,
        (conflict_id, conflict_type, severity, summary, now, json.dumps(metadata or {}, sort_keys=True)),
    )
    for item in items:
        connection.execute(
            """
            INSERT OR IGNORE INTO conflict_items(
              conflict_id, object_type, object_id, role, evidence_id, rationale_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                conflict_id,
                item["object_type"],
                item["object_id"],
                item.get("role", "candidate"),
                item.get("evidence_id", ""),
                json.dumps(item.get("rationale", {}), sort_keys=True),
            ),
        )
    return conflict_id


def scan_source_dedupe(connection: sqlite3.Connection, *, source_id: str = "", capture_id: str = "") -> list[str]:
    ensure_conflict_schema(connection)
    conflicts: list[str] = []
    source = None
    capture = None
    if source_id:
        source = connection.execute("SELECT * FROM source_registry WHERE id = ?", (source_id,)).fetchone()
    if capture_id:
        capture = connection.execute("SELECT * FROM source_captures WHERE id = ?", (capture_id,)).fetchone()
        if capture and not source:
            source = connection.execute("SELECT * FROM source_registry WHERE id = ?", (capture["source_id"],)).fetchone()
    if not source:
        return conflicts

    source_id = source["id"]
    source_canonical = canonical_url(source["canonical_ref"] or source["url"])
    source_title_key = normalize_entity_name(source["title"])
    for other in connection.execute("SELECT * FROM source_registry WHERE id != ? AND status IN ('active', 'stale_pending_refresh')", (source_id,)):
        other_canonical = canonical_url(other["canonical_ref"] or other["url"])
        other_title_key = normalize_entity_name(other["title"])
        exact_url = source_canonical and source_canonical == other_canonical
        title_match = source_title_key and other_title_key and similarity(source_title_key, other_title_key) >= 0.92
        if exact_url or (title_match and source["source_type"] == other["source_type"]):
            conflicts.append(
                insert_conflict(
                    connection,
                    conflict_type="duplicate_source",
                    severity="low",
                    summary=f"Possible duplicate source: {source['title']} overlaps {other['title']}.",
                    items=[
                        {"object_type": "source", "object_id": source_id, "role": "candidate", "rationale": {"title": source["title"]}},
                        {"object_type": "source", "object_id": other["id"], "role": "existing", "rationale": {"title": other["title"]}},
                    ],
                    metadata={"exact_url": bool(exact_url), "title_similarity": similarity(source_title_key, other_title_key)},
                )
            )

    if capture:
        for other in connection.execute(
            """
            SELECT *
            FROM source_captures
            WHERE id != ? AND content_hash = ?
            """,
            (capture["id"], capture["content_hash"]),
        ):
            conflicts.append(
                insert_conflict(
                    connection,
                    conflict_type="duplicate_content",
                    severity="low",
                    summary=f"Duplicate captured content hash for {capture['id']} and {other['id']}.",
                    items=[
                        {"object_type": "capture", "object_id": capture["id"], "role": "candidate"},
                        {"object_type": "capture", "object_id": other["id"], "role": "existing"},
                    ],
                    metadata={"content_hash": capture["content_hash"]},
                )
            )
    return conflicts


def aliases_for(connection: sqlite3.Connection, node_id: str) -> set[str]:
    return {
        normalize_entity_name(row["alias"])
        for row in connection.execute("SELECT alias FROM aliases WHERE node_id = ?", (node_id,))
        if normalize_entity_name(row["alias"])
    }


def live_nodes(connection: sqlite3.Connection, node_type: str, exclude_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM nodes
        WHERE type = ? AND id != ? AND status IN ('active', 'provisional')
        """,
        (node_type, exclude_id),
    ).fetchall()


def scan_entity_dedupe(connection: sqlite3.Connection, node_ids: Iterable[str]) -> list[str]:
    ensure_conflict_schema(connection)
    conflicts: list[str] = []
    for node_id in sorted(set(node_ids)):
        node = connection.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not node or node["status"] not in LIVE_STATUSES:
            continue
        node_name = normalize_entity_name(node["name"])
        node_aliases = aliases_for(connection, node_id) | {node_name}
        for other in live_nodes(connection, node["type"], node_id):
            other_name = normalize_entity_name(other["name"])
            other_aliases = aliases_for(connection, other["id"]) | {other_name}
            alias_overlap = bool((node_aliases - {""}) & (other_aliases - {""}))
            name_similarity = similarity(node_name, other_name)
            same_key = node_name and node_name == other_name
            if not (alias_overlap or same_key or name_similarity >= 0.90):
                continue
            conflicts.append(
                insert_conflict(
                    connection,
                    conflict_type="duplicate_entity",
                    severity="medium" if node["type"] in {"claim", "policy", "rule"} else "low",
                    summary=f"Possible duplicate {node['type']} entity: {node['name']} overlaps {other['name']}.",
                    items=[
                        {"object_type": "node", "object_id": node_id, "role": "candidate", "rationale": {"name": node["name"]}},
                        {"object_type": "node", "object_id": other["id"], "role": "existing", "rationale": {"name": other["name"]}},
                    ],
                    metadata={"name_similarity": name_similarity, "alias_overlap": alias_overlap},
                )
            )
    return conflicts


def infer_polarity(text: str) -> str:
    normalized = normalize_text(text)
    if re.search(r"\b(do not|don't|should not|must not|no longer|never|avoid|forbid|reject|disable|deprecated)\b", normalized):
        return "negative"
    if any(re.search(rf"\b{re.escape(term)}\b", normalized) for term in POSITIVE_TERMS):
        return "positive"
    return "neutral"


def subject_key(text: str) -> str:
    tokens = [token for token in normalize_text(text).split() if token not in SUBJECT_STOPWORDS and len(token) > 2]
    if not tokens:
        return ""
    deduped = sorted(dict.fromkeys(tokens))
    return " ".join(deduped[:10])


def node_claim_text(node: sqlite3.Row) -> str:
    summary = normalize_space(node["summary"])
    if node["type"] in CLAIM_NODE_TYPES:
        return summary or node["name"]
    if re.search(r"\b(should|must|avoid|recommend|prefer|do not|don't|never|requires?)\b", summary.lower()):
        return summary
    return ""


def upsert_claim_record(connection: sqlite3.Connection, node: sqlite3.Row) -> str | None:
    text = node_claim_text(node)
    if not text:
        return None
    normalized = normalize_text(text)
    subject = subject_key(text)
    if not subject:
        return None
    polarity = infer_polarity(text)
    claim_id = stable_id("claimrec", [node["id"], normalized[:400]])
    connection.execute(
        """
        INSERT INTO claim_records(
          id, node_id, claim_key, claim_text, normalized_text, subject_key,
          polarity, source_ref, confidence, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          claim_text=excluded.claim_text,
          normalized_text=excluded.normalized_text,
          subject_key=excluded.subject_key,
          polarity=excluded.polarity,
          source_ref=excluded.source_ref,
          confidence=excluded.confidence,
          status=excluded.status,
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            claim_id,
            node["id"],
            subject,
            text,
            normalized,
            subject,
            polarity,
            node["source_ref"],
            node["confidence"],
            node["status"],
        ),
    )
    return claim_id


def refresh_claim_records(connection: sqlite3.Connection) -> None:
    ensure_conflict_schema(connection)
    for node in connection.execute("SELECT * FROM nodes WHERE status IN ('active', 'provisional')"):
        upsert_claim_record(connection, node)


def scan_claim_conflicts(connection: sqlite3.Connection, node_ids: Iterable[str]) -> list[str]:
    ensure_conflict_schema(connection)
    refresh_claim_records(connection)
    conflicts: list[str] = []
    claim_rows = []
    for node_id in sorted(set(node_ids)):
        claim_rows.extend(connection.execute("SELECT * FROM claim_records WHERE node_id = ?", (node_id,)).fetchall())
    for claim in claim_rows:
        if claim["polarity"] not in {"positive", "negative"}:
            continue
        opposite = "negative" if claim["polarity"] == "positive" else "positive"
        for other in connection.execute(
            """
            SELECT *
            FROM claim_records
            WHERE node_id != ?
              AND subject_key = ?
              AND polarity = ?
              AND status IN ('active', 'provisional')
            """,
            (claim["node_id"], claim["subject_key"], opposite),
        ):
            conflicts.append(
                insert_conflict(
                    connection,
                    conflict_type="contradiction",
                    severity="high",
                    summary=f"Possible contradiction about `{claim['subject_key']}`.",
                    items=[
                        {
                            "object_type": "node",
                            "object_id": claim["node_id"],
                            "role": claim["polarity"],
                            "rationale": {"claim_text": claim["claim_text"]},
                        },
                        {
                            "object_type": "node",
                            "object_id": other["node_id"],
                            "role": other["polarity"],
                            "rationale": {"claim_text": other["claim_text"]},
                        },
                    ],
                    metadata={"subject_key": claim["subject_key"]},
                )
            )
    return conflicts


def change_set_node_ids(connection: sqlite3.Connection, change_set_id: str) -> list[str]:
    return [
        row["object_id"]
        for row in connection.execute(
            """
            SELECT DISTINCT object_id
            FROM graph_change_items
            WHERE change_set_id = ? AND object_type = 'node'
            """,
            (change_set_id,),
        )
    ]


def scan_change_set(connection: sqlite3.Connection, change_set_id: str, *, phase: str = "apply") -> list[str]:
    ensure_conflict_schema(connection)
    change_set = connection.execute("SELECT * FROM graph_change_sets WHERE id = ?", (change_set_id,)).fetchone()
    if not change_set:
        return []
    conflicts: list[str] = []
    conflicts.extend(
        scan_source_dedupe(
            connection,
            source_id=change_set["source_id"],
            capture_id=change_set["capture_id"],
        )
    )
    node_ids = change_set_node_ids(connection, change_set_id)
    conflicts.extend(scan_entity_dedupe(connection, node_ids))
    conflicts.extend(scan_claim_conflicts(connection, node_ids))
    if conflicts:
        try:
            metadata = json.loads(change_set["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        metadata["conflict_scan"] = {"phase": phase, "conflict_ids": sorted(set(conflicts))}
        connection.execute(
            """
            UPDATE graph_change_sets SET metadata_json = ? WHERE id = ?
            """,
            (json.dumps(metadata, sort_keys=True), change_set_id),
        )
    return sorted(set(conflicts))


def open_conflicts_for_objects(connection: sqlite3.Connection, refs: Iterable[tuple[str, str]], limit: int = 5) -> list[sqlite3.Row]:
    if not has_conflict_schema(connection):
        return []
    pairs = [(object_type, object_id) for object_type, object_id in refs if object_type and object_id]
    if not pairs:
        return []
    clauses = " OR ".join("(ci.object_type = ? AND ci.object_id = ?)" for _ in pairs)
    params: list[str] = []
    for object_type, object_id in pairs:
        params.extend([object_type, object_id])
    params.append(limit)
    return connection.execute(
        f"""
        SELECT DISTINCT cr.*
        FROM conflict_records cr
        JOIN conflict_items ci ON ci.conflict_id = cr.id
        WHERE cr.status IN ('open', 'acknowledged') AND ({clauses})
        ORDER BY
          CASE cr.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
          cr.detected_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def open_conflict_count(connection: sqlite3.Connection) -> int:
    if not has_conflict_schema(connection):
        return 0
    row = connection.execute(
        "SELECT COUNT(*) AS count FROM conflict_records WHERE status IN ('open', 'acknowledged')"
    ).fetchone()
    return int(row["count"])


def open_conflict_rows(connection: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    if not has_conflict_schema(connection):
        return []
    return connection.execute(
        """
        SELECT *
        FROM conflict_records
        WHERE status IN ('open', 'acknowledged')
        ORDER BY
          CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
          detected_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
