#!/usr/bin/env python3
"""Promote or deprecate objects from an audited SkillGraph change set."""

from __future__ import annotations

import argparse

from conflict_ledger import scan_change_set
from graph_audit import change_change_set_object_statuses
from praxis.paths import kg_dir
from research_common import DEFAULT_ROOT, connect


def status_for_command(command: str) -> str:
    if command == "promote":
        return "active"
    if command == "deprecate":
        return "deprecated"
    raise ValueError(f"Unsupported status command: {command}")


def main(argv: list[str] | None = None, *, command: str | None = None) -> int:
    parser = argparse.ArgumentParser(prog=f"praxis {command}" if command else None, description=__doc__)
    if command is None:
        parser.add_argument("command", choices=["promote", "deprecate"], help="Lifecycle action to apply.")
    parser.add_argument("change_set", help="Source graph_change_sets.id whose objects should be updated.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--actor", default="praxis")
    parser.add_argument("--skip-evidence", action="store_true", help="Only update nodes/edges, leaving evidence status unchanged.")
    args = parser.parse_args(argv)

    action = command or args.command
    status = status_for_command(action)
    db_path = kg_dir(args.root) / "skill_graph.sqlite"
    with connect(db_path) as connection:
        try:
            count = change_change_set_object_statuses(
                connection,
                args.change_set,
                status=status,
                action=action,
                actor=args.actor,
                include_evidence=not args.skip_evidence,
            )
            conflict_ids = scan_change_set(connection, args.change_set, phase=action) if action == "promote" else []
        except ValueError as exc:
            print(str(exc))
            return 1

    print(f"{action.title()}d graph objects from change set: {args.change_set}")
    print(f"Objects changed: {count}")
    if conflict_ids:
        print("Conflict warnings:")
        for conflict_id in conflict_ids:
            print(f"- {conflict_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
