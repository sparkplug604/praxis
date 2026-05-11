#!/usr/bin/env python3
"""Search the local Praxis relational library."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from praxis.paths import default_root


DEFAULT_DB = default_root() / "db" / "praxis.sqlite"


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def search_sources(connection: sqlite3.Connection, query: str, limit: int) -> list[sqlite3.Row]:
    like = f"%{query}%"
    return connection.execute(
        """
        SELECT
          s.id, s.title, s.year, s.source_type, s.url, s.primary_focus,
          s.agent_relevance, s.engineering_relevance, s.evidence_strength,
          s.summary, s.critical_notes,
          group_concat(t.name, ', ') AS tags
        FROM sources s
        LEFT JOIN source_tags st ON st.source_id = s.id
        LEFT JOIN tags t ON t.id = st.tag_id
        WHERE
          s.title LIKE ?
          OR s.summary LIKE ?
          OR s.critical_notes LIKE ?
          OR s.primary_focus LIKE ?
          OR t.name LIKE ?
        GROUP BY s.id
        ORDER BY s.agent_relevance DESC, s.engineering_relevance DESC, s.year DESC
        LIMIT ?
        """,
        (like, like, like, like, like, limit),
    ).fetchall()


def search_patterns(connection: sqlite3.Connection, query: str, limit: int) -> list[sqlite3.Row]:
    like = f"%{query}%"
    return connection.execute(
        """
        SELECT id, name, category, description, agent_rule, runtime_rule, maturity
        FROM patterns
        WHERE name LIKE ? OR category LIKE ? OR description LIKE ? OR agent_rule LIKE ? OR runtime_rule LIKE ?
        ORDER BY category, name
        LIMIT ?
        """,
        (like, like, like, like, like, limit),
    ).fetchall()


def search_failure_modes(connection: sqlite3.Connection, query: str, limit: int) -> list[sqlite3.Row]:
    like = f"%{query}%"
    return connection.execute(
        """
        SELECT id, name, description, detection, mitigation, severity
        FROM failure_modes
        WHERE name LIKE ? OR description LIKE ? OR detection LIKE ? OR mitigation LIKE ?
        ORDER BY severity DESC, name
        LIMIT ?
        """,
        (like, like, like, like, limit),
    ).fetchall()


def print_sources(rows: list[sqlite3.Row]) -> None:
    print("# Sources\n")
    if not rows:
        print("No matching sources.\n")
        return
    for row in rows:
        print(f"## {row['title']} ({row['year'] or 'n.d.'})")
        print(f"- id: `{row['id']}`")
        print(f"- type: {row['source_type']}")
        print(f"- focus: {row['primary_focus']}")
        print(f"- scores: agent={row['agent_relevance']} engineering={row['engineering_relevance']} evidence={row['evidence_strength']}")
        if row["tags"]:
            print(f"- tags: {row['tags']}")
        print(f"- url: {row['url']}")
        print(f"- summary: {row['summary']}")
        if row["critical_notes"]:
            print(f"- critical notes: {row['critical_notes']}")
        print()


def print_patterns(rows: list[sqlite3.Row]) -> None:
    print("# Patterns\n")
    if not rows:
        print("No matching patterns.\n")
        return
    for row in rows:
        print(f"## {row['name']}")
        print(f"- id: `{row['id']}`")
        print(f"- category: {row['category']}")
        print(f"- maturity: {row['maturity']}")
        print(f"- description: {row['description']}")
        print(f"- Agent rule: {row['agent_rule']}")
        if row["runtime_rule"]:
            print(f"- Runtime rule: {row['runtime_rule']}")
        print()


def print_failure_modes(rows: list[sqlite3.Row]) -> None:
    print("# Failure Modes\n")
    if not rows:
        print("No matching failure modes.\n")
        return
    for row in rows:
        print(f"## {row['name']}")
        print(f"- id: `{row['id']}`")
        print(f"- severity: {row['severity']}")
        print(f"- description: {row['description']}")
        print(f"- detection: {row['detection']}")
        print(f"- mitigation: {row['mitigation']}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Search query")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite DB")
    parser.add_argument("--limit", type=int, default=8, help="Results per section")
    parser.add_argument(
        "--section",
        choices=["all", "sources", "patterns", "failure_modes"],
        default="all",
        help="Restrict search section",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    with connect(db_path) as connection:
        if args.section in ("all", "sources"):
            print_sources(search_sources(connection, args.query, args.limit))
        if args.section in ("all", "patterns"):
            print_patterns(search_patterns(connection, args.query, args.limit))
        if args.section in ("all", "failure_modes"):
            print_failure_modes(search_failure_modes(connection, args.query, args.limit))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
