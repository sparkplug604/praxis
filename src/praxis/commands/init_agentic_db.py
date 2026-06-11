#!/usr/bin/env python3
"""Initialize the Praxis SQLite database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from praxis.paths import bootstrap_path, db_dir, default_root


DEFAULT_ROOT = default_root()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_tag(connection: sqlite3.Connection, name: str) -> int:
    connection.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    row = connection.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


def upsert_source(connection: sqlite3.Connection, source: dict) -> None:
    columns = [
        "id",
        "title",
        "year",
        "source_type",
        "venue",
        "url",
        "arxiv_id",
        "repo_url",
        "primary_focus",
        "agent_relevance",
        "engineering_relevance",
        "evidence_strength",
        "reproducibility",
        "safety_relevance",
        "summary",
        "critical_notes",
        "status",
    ]
    values = [source.get(column, "") for column in columns]
    values[2] = source.get("year")
    values[-1] = source.get("status", "seeded")
    placeholders = ", ".join("?" for _ in columns)
    update = ", ".join(f"{column}=excluded.{column}" for column in columns[1:])
    connection.execute(
        f"""
        INSERT INTO sources({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(id) DO UPDATE SET {update}, updated_at=CURRENT_TIMESTAMP
        """,
        values,
    )

    connection.execute("DELETE FROM source_tags WHERE source_id = ?", (source["id"],))
    for tag in source.get("tags", []):
        tag_id = ensure_tag(connection, tag)
        connection.execute(
            "INSERT OR IGNORE INTO source_tags(source_id, tag_id) VALUES (?, ?)",
            (source["id"], tag_id),
        )


def upsert_pattern(connection: sqlite3.Connection, pattern: dict) -> None:
    connection.execute(
        """
        INSERT INTO patterns(id, name, category, description, agent_rule, runtime_rule, maturity)
        VALUES (:id, :name, :category, :description, :agent_rule, :runtime_rule, :maturity)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          category=excluded.category,
          description=excluded.description,
          agent_rule=excluded.agent_rule,
          runtime_rule=excluded.runtime_rule,
          maturity=excluded.maturity
        """,
        pattern,
    )


def upsert_failure_mode(connection: sqlite3.Connection, failure_mode: dict) -> None:
    connection.execute(
        """
        INSERT INTO failure_modes(id, name, description, detection, mitigation, severity)
        VALUES (:id, :name, :description, :detection, :mitigation, :severity)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          description=excluded.description,
          detection=excluded.detection,
          mitigation=excluded.mitigation,
          severity=excluded.severity
        """,
        failure_mode,
    )


def upsert_benchmark(connection: sqlite3.Connection, benchmark: dict) -> None:
    connection.execute(
        """
        INSERT INTO benchmarks(id, name, domain, url, measures, strengths, limitations, agent_use)
        VALUES (:id, :name, :domain, :url, :measures, :strengths, :limitations, :agent_use)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          domain=excluded.domain,
          url=excluded.url,
          measures=excluded.measures,
          strengths=excluded.strengths,
          limitations=excluded.limitations,
          agent_use=excluded.agent_use
        """,
        benchmark,
    )


def upsert_agent_practice(connection: sqlite3.Connection, practice: dict) -> None:
    connection.execute(
        """
        INSERT INTO agent_practices(id, name, trigger, practice, anti_pattern, evidence_basis)
        VALUES (:id, :name, :trigger, :practice, :anti_pattern, :evidence_basis)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          trigger=excluded.trigger,
          practice=excluded.practice,
          anti_pattern=excluded.anti_pattern,
          evidence_basis=excluded.evidence_basis
        """,
        practice,
    )


def link_source_patterns(connection: sqlite3.Connection, source: dict) -> None:
    connection.execute("DELETE FROM source_patterns WHERE source_id = ?", (source["id"],))
    for pattern_id in source.get("patterns", []):
        connection.execute(
            """
            INSERT OR IGNORE INTO source_patterns(source_id, pattern_id)
            VALUES (?, ?)
            """,
            (source["id"], pattern_id),
        )


def insert_claims(connection: sqlite3.Connection, source: dict) -> None:
    connection.execute("DELETE FROM claims WHERE source_id = ?", (source["id"],))
    for claim in source.get("claims", []):
        connection.execute(
            """
            INSERT INTO claims(source_id, claim, evidence, limitation, agent_implication, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source["id"],
                claim.get("claim", ""),
                claim.get("evidence", ""),
                claim.get("limitation", ""),
                claim.get("agent_implication", ""),
                claim.get("confidence", "medium"),
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    args = parser.parse_args()

    root = Path(args.root)
    schema_path = bootstrap_path(root, "db", "schema.sql")
    seed_path = bootstrap_path(root, "sources", "seed_sources.json")
    db_path = db_dir(root) / "praxis.sqlite"

    seed = json.loads(seed_path.read_text())
    with connect(db_path) as connection:
        connection.executescript(schema_path.read_text())

        for pattern in seed.get("patterns", []):
            upsert_pattern(connection, pattern)
        for failure_mode in seed.get("failure_modes", []):
            upsert_failure_mode(connection, failure_mode)
        for benchmark in seed.get("benchmarks", []):
            upsert_benchmark(connection, benchmark)
        for practice in seed.get("agent_practices", []):
            upsert_agent_practice(connection, practice)

        for source in seed.get("sources", []):
            upsert_source(connection, source)
            link_source_patterns(connection, source)
            insert_claims(connection, source)

    print(f"Initialized {db_path}")
    print(f"Sources: {len(seed.get('sources', []))}")
    print(f"Patterns: {len(seed.get('patterns', []))}")
    print(f"Failure modes: {len(seed.get('failure_modes', []))}")
    print(f"Benchmarks: {len(seed.get('benchmarks', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
