#!/usr/bin/env python3
"""Inspect and apply reversible dedupe actions for Praxis conflicts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from conflict_ledger import DEDUP_TYPES, ensure_conflict_schema
from graph_audit import create_change_set, fetch_graph_object, log_change_item, mark_graph_object_status, rollback_change_set
from init_skill_graph import upsert_node
from research_common import DEFAULT_ROOT, connect, utc_now


def conflict_items(connection, conflict_id: str) -> list:
    return connection.execute(
        """
        SELECT *
        FROM conflict_items
        WHERE conflict_id = ?
        ORDER BY object_type, role, object_id
        """,
        (conflict_id,),
    ).fetchall()


def cmd_list(args: argparse.Namespace) -> int:
    db_path = Path(args.root) / "kg" / "skill_graph.sqlite"
    with connect(db_path) as connection:
        ensure_conflict_schema(connection)
        placeholders = ", ".join("?" for _ in DEDUP_TYPES)
        rows = connection.execute(
            f"""
            SELECT *
            FROM conflict_records
            WHERE status IN ('open', 'acknowledged')
              AND conflict_type IN ({placeholders})
            ORDER BY detected_at DESC
            LIMIT ?
            """,
            (*DEDUP_TYPES, args.limit),
        ).fetchall()
    if not rows:
        print("No open dedupe candidates.")
        return 0
    for row in rows:
        print(f"- {row['id']}")
        print(f"  type: {row['conflict_type']}")
        print(f"  severity: {row['severity']}")
        print(f"  summary: {row['summary']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    db_path = Path(args.root) / "kg" / "skill_graph.sqlite"
    with connect(db_path) as connection:
        ensure_conflict_schema(connection)
        row = connection.execute("SELECT * FROM conflict_records WHERE id = ?", (args.conflict,)).fetchone()
        if not row:
            print(f"Dedupe conflict not found: {args.conflict}")
            return 1
        print(f"# {row['id']}\n")
        print(f"- type: {row['conflict_type']}")
        print(f"- status: {row['status']}")
        print(f"- summary: {row['summary']}")
        print("\n## Items\n")
        for item in conflict_items(connection, args.conflict):
            print(f"- {item['object_type']} `{item['object_id']}` ({item['role']})")
            if item["rationale_json"] and item["rationale_json"] != "{}":
                print(f"  rationale: {item['rationale_json']}")
    return 0


def node_payload_with_aliases(connection, node_id: str) -> dict:
    payload = fetch_graph_object(connection, "node", node_id)
    if not payload:
        raise ValueError(f"Node not found: {node_id}")
    return payload


def merge_nodes(connection, conflict_id: str, canonical_id: str | None, actor: str) -> str:
    ensure_conflict_schema(connection)
    conflict = connection.execute("SELECT * FROM conflict_records WHERE id = ?", (conflict_id,)).fetchone()
    if not conflict:
        raise ValueError(f"Conflict not found: {conflict_id}")
    if conflict["conflict_type"] != "duplicate_entity":
        raise ValueError("Only duplicate_entity conflicts can be merged into graph nodes.")

    items = [item for item in conflict_items(connection, conflict_id) if item["object_type"] == "node"]
    if len(items) < 2:
        raise ValueError("Dedupe merge needs at least two node items.")

    if not canonical_id:
        existing = [item for item in items if item["role"] == "existing"]
        canonical_id = existing[0]["object_id"] if existing else items[0]["object_id"]

    duplicate_ids = [item["object_id"] for item in items if item["object_id"] != canonical_id]
    if not duplicate_ids:
        raise ValueError("No duplicate nodes remain after choosing canonical id.")

    canonical_before = node_payload_with_aliases(connection, canonical_id)
    aliases = set(canonical_before.get("aliases", []))
    tags = set(canonical_before.get("tags", []))
    tags.add("dedupe-canonical")
    for duplicate_id in duplicate_ids:
        duplicate = node_payload_with_aliases(connection, duplicate_id)
        aliases.update(duplicate.get("aliases", []))
        aliases.add(duplicate["id"])
        aliases.add(duplicate["name"])
    canonical_after = {
        **canonical_before,
        "aliases": sorted(alias for alias in aliases if alias),
        "tags": sorted(tag for tag in tags if tag),
    }

    change_set_id = create_change_set(
        connection,
        action="dedupe_merge",
        mode="manual",
        title=f"Merge duplicate entities for {conflict_id}",
        summary=f"Merge duplicate entity candidates into {canonical_id}.",
        actor=actor,
        metadata={"conflict_id": conflict_id, "canonical_id": canonical_id, "duplicate_ids": duplicate_ids},
    )

    before = fetch_graph_object(connection, "node", canonical_id)
    upsert_node(connection, canonical_after)
    after = fetch_graph_object(connection, "node", canonical_id)
    log_change_item(
        connection,
        change_set_id=change_set_id,
        object_type="node",
        object_id=canonical_id,
        operation="dedupe:canonicalize",
        before=before,
        after=after,
    )

    for duplicate_id in duplicate_ids:
        before = fetch_graph_object(connection, "node", duplicate_id)
        mark_graph_object_status(connection, "node", duplicate_id, "merged")
        after = fetch_graph_object(connection, "node", duplicate_id)
        log_change_item(
            connection,
            change_set_id=change_set_id,
            object_type="node",
            object_id=duplicate_id,
            operation="dedupe:merge",
            before=before,
            after=after,
        )

    metadata = json.loads(conflict["metadata_json"] or "{}")
    metadata["merge_change_set"] = change_set_id
    metadata["canonical_id"] = canonical_id
    connection.execute(
        """
        UPDATE conflict_records
        SET status = 'resolved',
            resolved_at = ?,
            resolution = 'merge_entities',
            resolver_notes = ?,
            metadata_json = ?
        WHERE id = ?
        """,
        (
            utc_now(),
            f"Merged into {canonical_id}. Revert with praxis dedupe split {change_set_id}.",
            json.dumps(metadata, sort_keys=True),
            conflict_id,
        ),
    )
    return change_set_id


def cmd_merge(args: argparse.Namespace) -> int:
    db_path = Path(args.root) / "kg" / "skill_graph.sqlite"
    with connect(db_path) as connection:
        try:
            change_set_id = merge_nodes(connection, args.conflict, args.canonical, args.actor)
        except ValueError as exc:
            print(str(exc))
            return 1
    print(f"Merged duplicate entity conflict: {args.conflict}")
    print(f"change_set_id: {change_set_id}")
    print("Undo if needed:")
    print(f"  praxis dedupe split {change_set_id}")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    db_path = Path(args.root) / "kg" / "skill_graph.sqlite"
    with connect(db_path) as connection:
        try:
            count = rollback_change_set(connection, args.change_set, actor=args.actor, force=args.force)
        except Exception as exc:
            print(str(exc))
            return 1
        reopened = 0
        ensure_conflict_schema(connection)
        for row in connection.execute("SELECT id, metadata_json FROM conflict_records WHERE resolution = 'merge_entities'"):
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                continue
            if metadata.get("merge_change_set") != args.change_set:
                continue
            connection.execute(
                """
                UPDATE conflict_records
                SET status = 'open',
                    resolved_at = NULL,
                    resolution = '',
                    resolver_notes = ?
                WHERE id = ?
                """,
                (f"Reopened after split of {args.change_set}.", row["id"]),
            )
            reopened += 1
    print(f"Reverted dedupe merge: {args.change_set}")
    print(f"Objects restored: {count}")
    if reopened:
        print(f"Reopened dedupe conflicts: {reopened}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List open dedupe candidates")
    list_parser.add_argument("--limit", type=int, default=25)
    list_parser.set_defaults(func=cmd_list)

    show_parser = subparsers.add_parser("show", help="Show a dedupe candidate")
    show_parser.add_argument("conflict")
    show_parser.set_defaults(func=cmd_show)

    merge_parser = subparsers.add_parser("merge", help="Merge duplicate entity nodes from a dedupe conflict")
    merge_parser.add_argument("conflict")
    merge_parser.add_argument("--canonical", help="Canonical node id. Defaults to the existing node in the conflict.")
    merge_parser.add_argument("--actor", default="praxis")
    merge_parser.set_defaults(func=cmd_merge)

    split_parser = subparsers.add_parser("split", help="Undo a dedupe merge by rolling back its change set")
    split_parser.add_argument("change_set")
    split_parser.add_argument("--actor", default="praxis")
    split_parser.add_argument("--force", action="store_true")
    split_parser.set_defaults(func=cmd_split)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
