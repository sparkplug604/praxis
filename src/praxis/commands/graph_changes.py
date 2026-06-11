#!/usr/bin/env python3
"""Inspect audited SkillGraph change sets."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from graph_audit import ensure_audit_schema
from praxis.paths import default_root, kg_dir


DEFAULT_DB = kg_dir(default_root()) / "skill_graph.sqlite"


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def cmd_list(args: argparse.Namespace) -> int:
    with connect(Path(args.db)) as connection:
        ensure_audit_schema(connection)
        params: list[object] = []
        where = ""
        if args.status:
            where = "WHERE status = ?"
            params.append(args.status)
        params.append(args.limit)
        rows = connection.execute(
            f"""
            SELECT *
            FROM graph_change_sets
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    if not rows:
        print("No graph change sets found.")
        return 0
    for row in rows:
        print(f"{row['id']}")
        print(f"  title: {row['title']}")
        print(f"  action: {row['action']} ({row['mode']})")
        print(f"  status: {row['status']}")
        print(f"  capture_id: {row['capture_id'] or 'n/a'}")
        print(f"  created_at: {row['created_at']}")
        if row["reverted_at"]:
            print(f"  reverted_at: {row['reverted_at']}")
        print()
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    with connect(Path(args.db)) as connection:
        ensure_audit_schema(connection)
        change_set = connection.execute("SELECT * FROM graph_change_sets WHERE id = ?", (args.change_set,)).fetchone()
        if not change_set:
            print(f"Change set not found: {args.change_set}")
            return 1
        items = connection.execute(
            """
            SELECT *
            FROM graph_change_items
            WHERE change_set_id = ?
            ORDER BY created_at, id
            """,
            (args.change_set,),
        ).fetchall()

    print(f"# {change_set['title']}\n")
    print(f"- id: `{change_set['id']}`")
    print(f"- action: {change_set['action']}")
    print(f"- mode: {change_set['mode']}")
    print(f"- status: {change_set['status']}")
    print(f"- source_id: {change_set['source_id'] or 'n/a'}")
    print(f"- capture_id: {change_set['capture_id'] or 'n/a'}")
    print(f"- proposal_id: {change_set['proposal_id'] or 'n/a'}")
    print(f"- created_at: {change_set['created_at']}")
    if change_set["summary"]:
        print(f"- summary: {change_set['summary']}")
    if change_set["metadata_json"] and args.show_metadata:
        print(f"- metadata: `{change_set['metadata_json']}`")
    print("\n## Items\n")
    if not items:
        print("No change items recorded.")
        return 0
    for item in items:
        print(f"- {item['operation']} {item['object_type']} `{item['object_id']}`")
        if args.show_json:
            before = json.loads(item["before_json"]) if item["before_json"] else None
            after = json.loads(item["after_json"]) if item["after_json"] else None
            print(f"  - before: `{json.dumps(before, sort_keys=True)}`")
            print(f"  - after: `{json.dumps(after, sort_keys=True)}`")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SkillGraph SQLite database")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List recent change sets")
    list_parser.add_argument("--status", default="", help="Filter by status, e.g. applied or reverted")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(func=cmd_list)

    show_parser = subparsers.add_parser("show", help="Show one change set")
    show_parser.add_argument("change_set")
    show_parser.add_argument("--show-json", action="store_true")
    show_parser.add_argument("--show-metadata", action="store_true")
    show_parser.set_defaults(func=cmd_show)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
