#!/usr/bin/env python3
"""List, inspect, resolve, and rescan Praxis conflict ledger records."""

from __future__ import annotations

import argparse
import json

from conflict_ledger import ensure_conflict_schema, scan_change_set, utc_now
from praxis.paths import kg_dir
from research_common import DEFAULT_ROOT, connect


def print_conflict(row) -> None:
    print(f"- {row['id']}")
    print(f"  type: {row['conflict_type']}")
    print(f"  severity: {row['severity']}")
    print(f"  status: {row['status']}")
    print(f"  summary: {row['summary']}")
    if row["resolution"]:
        print(f"  resolution: {row['resolution']}")


def cmd_list(args: argparse.Namespace) -> int:
    db_path = kg_dir(args.root) / "skill_graph.sqlite"
    with connect(db_path) as connection:
        ensure_conflict_schema(connection)
        clauses = []
        params: list[object] = []
        if args.status:
            clauses.append("status = ?")
            params.append(args.status)
        if args.type:
            clauses.append("conflict_type = ?")
            params.append(args.type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(args.limit)
        rows = connection.execute(
            f"""
            SELECT *
            FROM conflict_records
            {where}
            ORDER BY
              CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
              detected_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        if not rows:
            print("No conflicts found.")
            return 0
        for row in rows:
            print_conflict(row)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    db_path = kg_dir(args.root) / "skill_graph.sqlite"
    with connect(db_path) as connection:
        ensure_conflict_schema(connection)
        row = connection.execute("SELECT * FROM conflict_records WHERE id = ?", (args.conflict,)).fetchone()
        if not row:
            print(f"Conflict not found: {args.conflict}")
            return 1
        print("# Conflict\n")
        print_conflict(row)
        if row["resolver_notes"]:
            print(f"  notes: {row['resolver_notes']}")
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        if metadata:
            print(f"  metadata: {json.dumps(metadata, sort_keys=True)}")
        print("\n# Items\n")
        for item in connection.execute(
            """
            SELECT *
            FROM conflict_items
            WHERE conflict_id = ?
            ORDER BY object_type, role, object_id
            """,
            (args.conflict,),
        ):
            print(f"- {item['object_type']} `{item['object_id']}` ({item['role']})")
            if item["evidence_id"]:
                print(f"  evidence: {item['evidence_id']}")
            if item["rationale_json"] and item["rationale_json"] != "{}":
                print(f"  rationale: {item['rationale_json']}")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    db_path = kg_dir(args.root) / "skill_graph.sqlite"
    with connect(db_path) as connection:
        ensure_conflict_schema(connection)
        row = connection.execute("SELECT id FROM conflict_records WHERE id = ?", (args.conflict,)).fetchone()
        if not row:
            print(f"Conflict not found: {args.conflict}")
            return 1
        status = args.status
        connection.execute(
            """
            UPDATE conflict_records
            SET status = ?,
                resolved_at = ?,
                resolution = ?,
                resolver_notes = ?
            WHERE id = ?
            """,
            (status, utc_now(), args.resolution, args.notes, args.conflict),
        )
    print(f"Resolved conflict: {args.conflict}")
    print(f"status: {status}")
    print(f"resolution: {args.resolution}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    db_path = kg_dir(args.root) / "skill_graph.sqlite"
    with connect(db_path) as connection:
        conflicts = scan_change_set(connection, args.change_set, phase="manual-scan")
    if conflicts:
        print("Conflicts found:")
        for conflict_id in conflicts:
            print(f"- {conflict_id}")
    else:
        print("No conflicts found.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List conflict ledger records")
    list_parser.add_argument("--status", default="open", help="Filter by status. Use empty string for all statuses.")
    list_parser.add_argument("--type", default="", help="Filter by conflict type.")
    list_parser.add_argument("--limit", type=int, default=25)
    list_parser.set_defaults(func=cmd_list)

    show_parser = subparsers.add_parser("show", help="Show one conflict and its linked objects")
    show_parser.add_argument("conflict")
    show_parser.set_defaults(func=cmd_show)

    resolve_parser = subparsers.add_parser("resolve", help="Resolve or suppress a conflict")
    resolve_parser.add_argument("conflict")
    resolve_parser.add_argument("--resolution", required=True)
    resolve_parser.add_argument("--notes", default="")
    resolve_parser.add_argument("--status", choices=["resolved", "suppressed", "false_positive", "acknowledged"], default="resolved")
    resolve_parser.set_defaults(func=cmd_resolve)

    scan_parser = subparsers.add_parser("scan", help="Scan a change set for conflicts")
    scan_parser.add_argument("change_set")
    scan_parser.set_defaults(func=cmd_scan)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
