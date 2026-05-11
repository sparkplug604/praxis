#!/usr/bin/env python3
"""Create a reviewed-before-apply SkillGraph update proposal from a capture."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from research_common import DEFAULT_ROOT, connect, read_json, sha256_text, slug, summarize_text, utc_now, write_json


CONCEPT_KEYWORDS = [
    ("concept:deterministic-replay", ["deterministic replay", "replay", "reconstruct"]),
    ("concept:consent-bound-context", ["consent", "grant", "revocation", "purpose"]),
    ("concept:tamper-evident-audit", ["sigchain", "tamper", "audit", "ed25519", "hash chain", "append-only"]),
    ("concept:deterministic-policy-enforcement", ["deterministic policy", "policy enforcement", "formal verification", "z3", "opa", "cedar"]),
    ("concept:tool-guardrails", ["tool guard", "tool gating", "guardrail", "before execution", "pre-execution"]),
    ("concept:pre-work-sync", ["pre-work", "synchronization", "assumptions"]),
    ("concept:task-semantic-contract", ["task contract", "semantic contract", "acceptance criteria"]),
    ("concept:reasoning-branch-merge", ["branch", "merge", "rationale", "reasoning"]),
    ("concept:context-distillation", ["context distillation", "context compression", "context slice"]),
    ("concept:divergence-detection", ["divergence", "drift detection", "misalignment"]),
]


def capture_from_db(connection: sqlite3.Connection, capture_or_path: str) -> tuple[sqlite3.Row, sqlite3.Row]:
    row = connection.execute("SELECT * FROM source_captures WHERE id = ?", (capture_or_path,)).fetchone()
    if not row:
        path = Path(capture_or_path)
        if path.exists():
            metadata = read_json(path) if path.suffix == ".json" else {}
            capture_id = metadata.get("capture_id")
            if capture_id:
                row = connection.execute("SELECT * FROM source_captures WHERE id = ?", (capture_id,)).fetchone()
    if not row:
        raise SystemExit(f"Capture not found: {capture_or_path}")
    source = connection.execute("SELECT * FROM source_registry WHERE id = ?", (row["source_id"],)).fetchone()
    if not source:
        raise SystemExit(f"Source not found for capture: {row['source_id']}")
    return row, source


def confidence_from_source(source: sqlite3.Row) -> str:
    score = int(source["credibility_score"] or 0)
    if score >= 4:
        return "medium"
    if score >= 2:
        return "low"
    return "low"


def node_type_from_source(source: sqlite3.Row) -> str:
    source_type = source["source_type"]
    if source_type in {"repo", "package"}:
        return "tool"
    if source_type == "paper":
        return "source"
    if source_type == "docs":
        return "source"
    return "source"


def proposed_edges_for_text(source_node_id: str, text: str, evidence_id: str, confidence: str) -> list[dict]:
    lowered = text.lower()
    edges: list[dict] = []
    for concept_id, keywords in CONCEPT_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            edges.append(
                {
                    "source_id": source_node_id,
                    "relation": "relates_to",
                    "target_id": concept_id,
                    "evidence_id": evidence_id,
                    "summary": "Keyword-derived relation from captured source. Review before treating as architecture evidence.",
                    "confidence": confidence,
                    "weight": 0.5,
                }
            )
    return edges


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", help="Capture id or capture metadata JSON path")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--title")
    parser.add_argument("--risk-level", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--no-keyword-edges", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    db_path = root / "kg" / "skill_graph.sqlite"
    proposals_root = root / "research" / "proposals"

    with connect(db_path) as connection:
        capture, source = capture_from_db(connection, args.capture)
        raw_path = Path(capture["raw_path"])
        summary_path = Path(capture["summary_path"])
        raw_text = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else ""
        summary_text = summary_path.read_text(encoding="utf-8", errors="replace") if summary_path.exists() else summarize_text(raw_text)

        confidence = confidence_from_source(source)
        source_node_id = f"external:{slug(source['title'])}"
        evidence_id = f"ev:research:{slug(source['id'])}:{capture['content_hash'][:12]}"
        proposal_id = f"proposal:{slug(source['id'])}:{capture['content_hash'][:12]}"
        proposal_path = proposals_root / f"{slug(proposal_id)}.json"

        evidence = [
            {
                "id": evidence_id,
                "evidence_type": "research_capture",
                "title": f"Research capture: {source['title']}",
                "source_path": capture["summary_path"],
                "url": source["url"],
                "locator": capture["id"],
                "note": f"Captured through research_source.py at content hash {capture['content_hash']}.",
                "confidence": confidence,
            }
        ]
        nodes = [
            {
                "id": source_node_id,
                "type": node_type_from_source(source),
                "name": source["title"],
                "summary": summarize_text(summary_text, max_chars=700),
                "confidence": confidence,
                "source_ref": source["canonical_ref"],
                "aliases": [alias for alias in [source["id"], source["url"], source["canonical_ref"]] if alias],
                "tags": ["researched", source["source_type"]],
            }
        ]
        edges = [] if args.no_keyword_edges else proposed_edges_for_text(source_node_id, raw_text + "\n" + summary_text, evidence_id, confidence)

        proposal = {
            "id": proposal_id,
            "title": args.title or f"Graph update from {source['title']}",
            "created_at": utc_now(),
            "source_id": source["id"],
            "capture_id": capture["id"],
            "risk_level": args.risk_level,
            "status": "proposed",
            "summary": f"Adds/updates a researched node for {source['title']} and {len(edges)} keyword-derived relation(s).",
            "review_guidance": [
                "Check whether keyword-derived edges are truly supported by the source.",
                "Upgrade relation names from relates_to to implements/mitigates/supports only after evidence review.",
                "Delete weak edges before applying if the source is only marketing or secondary commentary."
            ],
            "evidence": evidence,
            "nodes": nodes,
            "edges": edges,
        }
        write_json(proposal_path, proposal)

        connection.execute(
            """
            INSERT INTO graph_update_proposals(
              id, source_id, capture_id, title, status, risk_level, proposal_path, summary
            )
            VALUES (?, ?, ?, ?, 'proposed', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title,
              status='proposed',
              risk_level=excluded.risk_level,
              proposal_path=excluded.proposal_path,
              summary=excluded.summary,
              reviewed_at=NULL,
              applied_at=NULL
            """,
            (
                proposal_id,
                source["id"],
                capture["id"],
                proposal["title"],
                args.risk_level,
                str(proposal_path),
                proposal["summary"],
            ),
        )

    print(f"Wrote proposal: {proposal_path}")
    print(f"proposal_id: {proposal_id}")
    print(f"nodes: {len(nodes)}")
    print(f"edges: {len(edges)}")
    print()
    print("Review, edit if needed, then apply:")
    print(f"  python3.12 \"{root / 'scripts' / 'apply_graph_update.py'}\" \"{proposal_path}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
