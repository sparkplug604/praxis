#!/usr/bin/env python3
"""Initialize the local SkillGraph SQLite database."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from praxis.paths import default_root


DEFAULT_ROOT = default_root()


def slug(text: str) -> str:
    out = []
    for char in text.lower().strip():
        if char.isalnum():
            out.append(char)
        elif char in ("-", "_", " ", "/", ":"):
            out.append("-")
    collapsed = "-".join(part for part in "".join(out).split("-") if part)
    return collapsed or hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def edge_id(source_id: str, relation: str, target_id: str, evidence_id: str | None = None) -> str:
    raw = "|".join([source_id, relation, target_id, evidence_id or ""])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"edge:{slug(source_id)}:{slug(relation)}:{slug(target_id)}:{digest}"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_tag(connection: sqlite3.Connection, name: str) -> int:
    connection.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    row = connection.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


def upsert_node(connection: sqlite3.Connection, node: dict[str, Any]) -> None:
    payload = {
        "id": node["id"],
        "type": node["type"],
        "name": node["name"],
        "summary": node.get("summary", ""),
        "confidence": node.get("confidence", "medium"),
        "status": node.get("status", "active"),
        "source_ref": node.get("source_ref", ""),
    }
    connection.execute(
        """
        INSERT INTO nodes(id, type, name, summary, confidence, status, source_ref)
        VALUES (:id, :type, :name, :summary, :confidence, :status, :source_ref)
        ON CONFLICT(id) DO UPDATE SET
          type=excluded.type,
          name=excluded.name,
          summary=excluded.summary,
          confidence=excluded.confidence,
          status=excluded.status,
          source_ref=excluded.source_ref,
          updated_at=CURRENT_TIMESTAMP
        """,
        payload,
    )

    connection.execute("DELETE FROM aliases WHERE node_id = ?", (node["id"],))
    for alias in node.get("aliases", []):
        connection.execute(
            "INSERT OR IGNORE INTO aliases(node_id, alias) VALUES (?, ?)",
            (node["id"], alias),
        )

    connection.execute("DELETE FROM node_tags WHERE node_id = ?", (node["id"],))
    for tag in node.get("tags", []):
        tag_id = ensure_tag(connection, tag)
        connection.execute(
            "INSERT OR IGNORE INTO node_tags(node_id, tag_id) VALUES (?, ?)",
            (node["id"], tag_id),
        )


def upsert_evidence(connection: sqlite3.Connection, evidence: dict[str, Any]) -> None:
    payload = {
        "id": evidence["id"],
        "evidence_type": evidence["evidence_type"],
        "title": evidence["title"],
        "source_path": evidence.get("source_path", ""),
        "url": evidence.get("url", ""),
        "locator": evidence.get("locator", ""),
        "note": evidence.get("note", ""),
        "confidence": evidence.get("confidence", "medium"),
        "status": evidence.get("status", "active"),
    }
    connection.execute(
        """
        INSERT INTO evidence(id, evidence_type, title, source_path, url, locator, note, confidence, status)
        VALUES (:id, :evidence_type, :title, :source_path, :url, :locator, :note, :confidence, :status)
        ON CONFLICT(id) DO UPDATE SET
          evidence_type=excluded.evidence_type,
          title=excluded.title,
          source_path=excluded.source_path,
          url=excluded.url,
          locator=excluded.locator,
          note=excluded.note,
          confidence=excluded.confidence,
          status=excluded.status,
          updated_at=CURRENT_TIMESTAMP
        """,
        payload,
    )


def upsert_edge(connection: sqlite3.Connection, edge: dict[str, Any]) -> None:
    evidence_id = edge.get("evidence_id") or None
    payload = {
        "id": edge.get("id") or edge_id(edge["source_id"], edge["relation"], edge["target_id"], evidence_id),
        "source_id": edge["source_id"],
        "relation": edge["relation"],
        "target_id": edge["target_id"],
        "evidence_id": evidence_id,
        "summary": edge.get("summary", ""),
        "confidence": edge.get("confidence", "medium"),
        "weight": float(edge.get("weight", 1.0)),
        "status": edge.get("status", "active"),
    }
    connection.execute(
        """
        INSERT INTO edges(id, source_id, relation, target_id, evidence_id, summary, confidence, weight, status)
        VALUES (:id, :source_id, :relation, :target_id, :evidence_id, :summary, :confidence, :weight, :status)
        ON CONFLICT(source_id, relation, target_id, evidence_id) DO UPDATE SET
          summary=excluded.summary,
          confidence=excluded.confidence,
          weight=excluded.weight,
          status=excluded.status,
          updated_at=CURRENT_TIMESTAMP
        """,
        payload,
    )


def import_relational_library(connection: sqlite3.Connection, library_db: Path) -> None:
    if not library_db.exists():
        return

    upsert_evidence(
        connection,
        {
            "id": "ev:praxis-db",
            "evidence_type": "local_database",
            "title": "Praxis database",
            "source_path": str(library_db.relative_to(DEFAULT_ROOT)) if library_db.is_relative_to(DEFAULT_ROOT) else library_db.name,
            "note": "Imported relational source, pattern, failure mode, benchmark, claim, and practice data.",
            "confidence": "high",
        },
    )

    with sqlite3.connect(library_db) as source:
        source.row_factory = sqlite3.Row

        for row in source.execute("SELECT * FROM sources"):
            upsert_node(
                connection,
                {
                    "id": f"source:{row['id']}",
                    "type": "source",
                    "name": row["title"],
                    "summary": row["summary"],
                    "confidence": "high" if row["evidence_strength"] >= 4 else "medium",
                    "source_ref": row["url"] or row["repo_url"] or "",
                    "aliases": [row["id"]],
                    "tags": ["imported-source", row["source_type"], row["primary_focus"]],
                },
            )

        for row in source.execute("SELECT * FROM patterns"):
            upsert_node(
                connection,
                {
                    "id": f"pattern:{row['id']}",
                    "type": "pattern",
                    "name": row["name"],
                    "summary": row["description"],
                    "confidence": "high" if row["maturity"] == "established" else "medium",
                    "aliases": [row["id"]],
                    "tags": ["imported-pattern", row["category"], row["maturity"]],
                },
            )

        for row in source.execute("SELECT * FROM failure_modes"):
            upsert_node(
                connection,
                {
                    "id": f"failure:{row['id']}",
                    "type": "failure_mode",
                    "name": row["name"],
                    "summary": row["description"],
                    "confidence": "medium",
                    "aliases": [row["id"]],
                    "tags": ["imported-failure-mode", row["severity"]],
                },
            )

        for row in source.execute("SELECT * FROM benchmarks"):
            upsert_node(
                connection,
                {
                    "id": f"benchmark:{row['id']}",
                    "type": "benchmark",
                    "name": row["name"],
                    "summary": row["measures"],
                    "confidence": "high",
                    "source_ref": row["url"] or "",
                    "aliases": [row["id"]],
                    "tags": ["imported-benchmark", row["domain"]],
                },
            )

        for row in source.execute("SELECT * FROM agent_practices"):
            upsert_node(
                connection,
                {
                    "id": f"practice:{row['id']}",
                    "type": "practice",
                    "name": row["name"],
                    "summary": row["practice"],
                    "confidence": "medium",
                    "aliases": [row["id"]],
                    "tags": ["imported-practice"],
                },
            )

        for row in source.execute("SELECT source_id, pattern_id, note FROM source_patterns"):
            upsert_edge(
                connection,
                {
                    "source_id": f"source:{row['source_id']}",
                    "relation": "supports",
                    "target_id": f"pattern:{row['pattern_id']}",
                    "evidence_id": "ev:praxis-db",
                    "summary": row["note"] or "Imported source-pattern relationship.",
                    "confidence": "medium",
                },
            )

        for row in source.execute("SELECT source_id, failure_mode_id, note FROM source_failure_modes"):
            upsert_edge(
                connection,
                {
                    "source_id": f"source:{row['source_id']}",
                    "relation": "documents",
                    "target_id": f"failure:{row['failure_mode_id']}",
                    "evidence_id": "ev:praxis-db",
                    "summary": row["note"] or "Imported source-failure relationship.",
                    "confidence": "medium",
                },
            )

        for row in source.execute("SELECT id, source_id, claim, confidence FROM claims"):
            claim_id = f"claim:{row['id']}"
            upsert_node(
                connection,
                {
                    "id": claim_id,
                    "type": "claim",
                    "name": row["claim"][:100],
                    "summary": row["claim"],
                    "confidence": row["confidence"] or "medium",
                    "tags": ["imported-claim"],
                },
            )
            upsert_edge(
                connection,
                {
                    "source_id": f"source:{row['source_id']}",
                    "relation": "supports",
                    "target_id": claim_id,
                    "evidence_id": "ev:praxis-db",
                    "summary": "Imported source-claim relationship.",
                    "confidence": row["confidence"] or "medium",
                },
            )


def print_counts(connection: sqlite3.Connection) -> None:
    for table in (
        "nodes",
        "edges",
        "evidence",
        "aliases",
        "tags",
        "node_tags",
        "source_registry",
        "source_captures",
        "graph_update_proposals",
        "graph_change_sets",
        "graph_change_items",
        "refresh_queue",
        "watchlist_runs",
        "research_hits",
    ):
        row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        print(f"{table}: {row['count']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--no-import-library-db", action="store_true", help="Skip importing the relational Praxis DB")
    args = parser.parse_args()

    root = Path(args.root)
    kg_dir = root / "kg"
    schema_path = kg_dir / "schema.sql"
    seed_path = kg_dir / "seed_graph.json"
    db_path = kg_dir / "skill_graph.sqlite"
    library_db = root / "db" / "praxis.sqlite"

    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    with connect(db_path) as connection:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        ensure_column(connection, "evidence", "status", "TEXT NOT NULL DEFAULT 'active'")
        for evidence in seed.get("evidence", []):
            upsert_evidence(connection, evidence)
        for node in seed.get("nodes", []):
            upsert_node(connection, node)
        for edge in seed.get("edges", []):
            upsert_edge(connection, edge)
        if not args.no_import_library_db:
            import_relational_library(connection, library_db)
        print(f"Initialized {db_path}")
        print_counts(connection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
