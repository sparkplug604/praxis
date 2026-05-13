#!/usr/bin/env python3
"""Apply a SkillGraph update proposal with an audit log."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from init_skill_graph import upsert_edge, upsert_evidence, upsert_node
from graph_audit import audited_upsert, create_change_set, ensure_audit_schema
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


def apply_proposal(
    *,
    root: Path,
    proposal_path: Path,
    proposal: dict,
    dry_run: bool = False,
    review_notes: str = "",
    allow_high_risk: bool = False,
    mode: str = "manual",
    actor: str = "praxis",
    archive: bool = True,
) -> dict:
    risk = proposal.get("risk_level", "medium")
    if risk == "high" and not allow_high_risk:
        raise PermissionError("Refusing to apply high-risk proposal without --allow-high-risk.")

    db_path = root / "kg" / "skill_graph.sqlite"
    applied_dir = root / "research" / "applied"

    with connect(db_path) as connection:
        ensure_audit_schema(connection)
        missing = ensure_edge_nodes_exist(connection, proposal)
        if missing:
            raise ValueError("Proposal references missing node ids: " + ", ".join(missing))

        if dry_run:
            return {
                "evidence": len(proposal.get("evidence", [])),
                "nodes": len(proposal.get("nodes", [])),
                "edges": len(proposal.get("edges", [])),
                "change_set_id": "",
                "applied_path": "",
            }

        proposal_id = proposal.get("id", "")
        change_set_id = create_change_set(
            connection,
            action="apply_graph_update",
            mode=mode,
            title=proposal.get("title", proposal_path.name),
            summary=proposal.get("summary", ""),
            source_id=proposal.get("source_id", ""),
            capture_id=proposal.get("capture_id", ""),
            proposal_id=proposal_id,
            actor=actor,
            metadata={"risk_level": risk, "proposal_path": str(proposal_path)},
        )

        for evidence in proposal.get("evidence", []):
            audited_upsert(
                connection,
                change_set_id=change_set_id,
                object_type="evidence",
                payload=evidence,
                upsert=upsert_evidence,
            )
        for node in proposal.get("nodes", []):
            audited_upsert(
                connection,
                change_set_id=change_set_id,
                object_type="node",
                payload=node,
                upsert=upsert_node,
            )
        for edge in proposal.get("edges", []):
            audited_upsert(
                connection,
                change_set_id=change_set_id,
                object_type="edge",
                payload=edge,
                upsert=upsert_edge,
            )

        now = utc_now()
        if proposal_id:
            connection.execute(
                """
                UPDATE graph_update_proposals
                SET status = ?,
                    review_notes = ?,
                    reviewed_at = COALESCE(reviewed_at, ?),
                    applied_at = ?
                WHERE id = ?
                """,
                ("auto_applied" if mode == "auto" else "applied", review_notes, now, now, proposal_id),
            )

        applied_path = ""
        if archive:
            applied_dir.mkdir(parents=True, exist_ok=True)
            target_name = proposal_path.name
            if mode == "auto" and not target_name.startswith("auto-"):
                target_name = f"auto-{target_name}"
            applied = applied_dir / target_name
            shutil.copy2(proposal_path, applied)
            applied_path = str(applied)

    return {
        "evidence": len(proposal.get("evidence", [])),
        "nodes": len(proposal.get("nodes", [])),
        "edges": len(proposal.get("edges", [])),
        "change_set_id": change_set_id,
        "applied_path": applied_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal", help="Proposal JSON path")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--review-notes", default="")
    parser.add_argument("--mode", choices=["manual", "auto"], default="manual", help="Record whether this was manual or automatic.")
    parser.add_argument("--actor", default="praxis")
    parser.add_argument("--allow-high-risk", action="store_true", help="Allow applying high-risk proposals")
    args = parser.parse_args()

    root = Path(args.root)
    proposal_path = Path(args.proposal)
    proposal = read_json(proposal_path)
    try:
        result = apply_proposal(
            root=root,
            proposal_path=proposal_path,
            proposal=proposal,
            dry_run=args.dry_run,
            review_notes=args.review_notes,
            allow_high_risk=args.allow_high_risk,
            mode=args.mode,
            actor=args.actor,
        )
    except PermissionError as exc:
        print(str(exc))
        return 2
    except ValueError as exc:
        print(str(exc))
        return 1

    print(f"Proposal: {proposal.get('title', proposal_path.name)}")
    print(f"- evidence: {result['evidence']}")
    print(f"- nodes: {result['nodes']}")
    print(f"- edges: {result['edges']}")
    if args.dry_run:
        print("Dry run only. No graph updates applied.")
        return 0
    print(f"Applied proposal: {proposal_path}")
    print(f"change_set_id: {result['change_set_id']}")
    if result["applied_path"]:
        print(f"Archived copy: {result['applied_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
