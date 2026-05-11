#!/usr/bin/env python3
"""Apply a reviewed SkillGraph update proposal."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from init_skill_graph import upsert_edge, upsert_evidence, upsert_node
from research_common import DEFAULT_ROOT, connect, read_json, utc_now


def ensure_edge_nodes_exist(connection, proposal: dict) -> list[str]:
    known = {row["id"] for row in connection.execute("SELECT id FROM nodes")}
    known.update(node["id"] for node in proposal.get("nodes", []))
    missing: list[str] = []
    for edge in proposal.get("edges", []):
        for key in ("source_id", "target_id"):
            if edge[key] not in known:
                missing.append(edge[key])
    return sorted(set(missing))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal", help="Proposal JSON path")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--review-notes", default="")
    parser.add_argument("--allow-high-risk", action="store_true", help="Allow applying high-risk proposals")
    args = parser.parse_args()

    root = Path(args.root)
    proposal_path = Path(args.proposal)
    proposal = read_json(proposal_path)
    risk = proposal.get("risk_level", "medium")
    if risk == "high" and not args.allow_high_risk:
        print("Refusing to apply high-risk proposal without --allow-high-risk.")
        return 2

    db_path = root / "kg" / "skill_graph.sqlite"
    applied_dir = root / "research" / "applied"

    with connect(db_path) as connection:
        missing = ensure_edge_nodes_exist(connection, proposal)
        if missing:
            print("Proposal references missing node ids:")
            for node_id in missing:
                print(f"- {node_id}")
            print("Add those nodes to the proposal before applying.")
            return 1

        print(f"Proposal: {proposal.get('title', proposal_path.name)}")
        print(f"- evidence: {len(proposal.get('evidence', []))}")
        print(f"- nodes: {len(proposal.get('nodes', []))}")
        print(f"- edges: {len(proposal.get('edges', []))}")
        if args.dry_run:
            print("Dry run only. No graph updates applied.")
            return 0

        for evidence in proposal.get("evidence", []):
            upsert_evidence(connection, evidence)
        for node in proposal.get("nodes", []):
            upsert_node(connection, node)
        for edge in proposal.get("edges", []):
            upsert_edge(connection, edge)

        proposal_id = proposal.get("id")
        now = utc_now()
        if proposal_id:
            connection.execute(
                """
                UPDATE graph_update_proposals
                SET status = 'applied',
                    review_notes = ?,
                    reviewed_at = COALESCE(reviewed_at, ?),
                    applied_at = ?
                WHERE id = ?
                """,
                (args.review_notes, now, now, proposal_id),
            )

        applied_dir.mkdir(parents=True, exist_ok=True)
        applied_path = applied_dir / proposal_path.name
        shutil.copy2(proposal_path, applied_path)

    print(f"Applied proposal: {proposal_path}")
    print(f"Archived copy: {applied_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
