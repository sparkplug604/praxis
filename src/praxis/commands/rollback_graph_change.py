#!/usr/bin/env python3
"""Rollback an audited SkillGraph change set."""

from __future__ import annotations

import argparse
from pathlib import Path

from graph_audit import rollback_change_set
from research_common import DEFAULT_ROOT, connect


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("change_set", help="graph_change_sets.id to rollback")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--actor", default="praxis")
    args = parser.parse_args()

    db_path = Path(args.root) / "kg" / "skill_graph.sqlite"
    with connect(db_path) as connection:
        try:
            count = rollback_change_set(connection, args.change_set, actor=args.actor)
        except ValueError as exc:
            print(str(exc))
            return 1

    if count == 0:
        print(f"Change set already reverted: {args.change_set}")
    else:
        print(f"Rolled back change set: {args.change_set}")
        print(f"Items reverted: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
