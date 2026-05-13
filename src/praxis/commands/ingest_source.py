#!/usr/bin/env python3
"""Capture a source and automatically apply a provisional SkillGraph update."""

from __future__ import annotations

import argparse
from pathlib import Path

from apply_graph_update import apply_proposal
from propose_graph_update import build_graph_proposal
from research_common import DEFAULT_ROOT
from research_source import capture_source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="URL, local file, or local directory to capture and ingest")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--title", help="Override source title")
    parser.add_argument("--source-type", help="Override source type")
    parser.add_argument("--source-id", help="Override source id")
    parser.add_argument("--freshness-window-days", type=int, default=30)
    parser.add_argument("--notes", default="")
    parser.add_argument("--risk-level", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--no-keyword-edges", action="store_true")
    parser.add_argument("--allow-high-risk", action="store_true", help="Allow auto-applying high-risk proposals")
    parser.add_argument("--actor", default="praxis")
    args = parser.parse_args()

    root = Path(args.root)
    capture = capture_source(
        root=root,
        source=args.source,
        title=args.title,
        source_type=args.source_type,
        source_id=args.source_id,
        freshness_window_days=args.freshness_window_days,
        notes=args.notes,
    )
    proposal_path, proposal = build_graph_proposal(
        root=root,
        capture_ref=str(capture["capture_id"]),
        title=f"Auto-ingest graph update from {capture['title']}",
        risk_level=args.risk_level,
        no_keyword_edges=args.no_keyword_edges,
        proposal_status="auto_proposed",
        graph_status="provisional",
    )
    try:
        result = apply_proposal(
            root=root,
            proposal_path=proposal_path,
            proposal=proposal,
            review_notes="Auto-applied by praxis ingest. Review, promote, deprecate, or rollback as needed.",
            allow_high_risk=args.allow_high_risk,
            mode="auto",
            actor=args.actor,
        )
    except PermissionError as exc:
        print(str(exc))
        print(f"Captured source and wrote proposal, but did not apply: {proposal_path}")
        return 2
    except ValueError as exc:
        print(str(exc))
        print(f"Captured source and wrote proposal, but did not apply: {proposal_path}")
        return 1

    print(f"Ingested {capture['title']}")
    print(f"source_id: {capture['source_id']}")
    print(f"capture_id: {capture['capture_id']}")
    print(f"proposal: {proposal_path}")
    print(f"change_set_id: {result['change_set_id']}")
    print(f"nodes: {result['nodes']}")
    print(f"edges: {result['edges']}")
    print()
    print("Rollback if needed:")
    print(f"  praxis rollback {result['change_set_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
