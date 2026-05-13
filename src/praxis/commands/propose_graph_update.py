#!/usr/bin/env python3
"""Create a SkillGraph update proposal from a capture."""

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


CONCEPT_SUMMARIES = {
    "concept:deterministic-replay": "Ability to reconstruct or replay a prior run from recorded state, inputs, and outputs.",
    "concept:consent-bound-context": "Context access constrained by permissions, revocation, and intended purpose.",
    "concept:tamper-evident-audit": "Audit records designed to make mutation history inspectable and difficult to alter silently.",
    "concept:deterministic-policy-enforcement": "Policy enforcement that behaves predictably and can be checked or reproduced.",
    "concept:tool-guardrails": "Controls around tool use before external side effects occur.",
    "concept:pre-work-sync": "Synchronization of assumptions, constraints, and intended outputs before parallel work starts.",
    "concept:task-semantic-contract": "Explicit contract describing task interpretation, dependencies, assumptions, and acceptance criteria.",
    "concept:reasoning-branch-merge": "Comparison and merge of rationale, assumptions, and outputs from parallel reasoning branches.",
    "concept:context-distillation": "Bounded context slicing that preserves important meaning while tracking loss.",
    "concept:divergence-detection": "Detection of incompatible assumptions, drift, or conflicting interpretations before commit time.",
}


def concept_name(concept_id: str) -> str:
    return concept_id.split(":", 1)[-1].replace("-", " ").title()


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


def proposed_edges_for_text(source_node_id: str, text: str, evidence_id: str, confidence: str, status: str) -> list[dict]:
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
                    "summary": "Keyword-derived relation from captured source. Treat as provisional until promoted or refined.",
                    "confidence": confidence,
                    "weight": 0.5,
                    "status": status,
                }
            )
    return edges


def missing_concept_nodes(connection: sqlite3.Connection, edges: list[dict], status: str) -> list[dict]:
    known = {row["id"] for row in connection.execute("SELECT id FROM nodes")}
    nodes = []
    for concept_id in sorted({edge["target_id"] for edge in edges if edge["target_id"].startswith("concept:")}):
        if concept_id in known:
            continue
        nodes.append(
            {
                "id": concept_id,
                "type": "concept",
                "name": concept_name(concept_id),
                "summary": CONCEPT_SUMMARIES.get(concept_id, "Auto-created concept node from source ingestion."),
                "confidence": "low",
                "status": status,
                "aliases": [concept_name(concept_id)],
                "tags": ["auto-concept", status],
            }
        )
    return nodes


def build_graph_proposal(
    *,
    root: Path,
    capture_ref: str,
    title: str | None = None,
    risk_level: str = "medium",
    no_keyword_edges: bool = False,
    proposal_status: str = "proposed",
    graph_status: str = "provisional",
) -> tuple[Path, dict]:
    db_path = root / "kg" / "skill_graph.sqlite"
    proposals_root = root / "research" / "proposals"

    with connect(db_path) as connection:
        capture, source = capture_from_db(connection, capture_ref)
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
                "status": graph_status,
            }
        ]
        nodes = [
            {
                "id": source_node_id,
                "type": node_type_from_source(source),
                "name": source["title"],
                "summary": summarize_text(summary_text, max_chars=700),
                "confidence": confidence,
                "status": graph_status,
                "source_ref": source["canonical_ref"],
                "aliases": [alias for alias in [source["id"], source["url"], source["canonical_ref"]] if alias],
                "tags": ["researched", source["source_type"], graph_status],
            }
        ]
        edges = [] if no_keyword_edges else proposed_edges_for_text(source_node_id, raw_text + "\n" + summary_text, evidence_id, confidence, graph_status)
        nodes.extend(missing_concept_nodes(connection, edges, graph_status))

        proposal = {
            "id": proposal_id,
            "title": title or f"Graph update from {source['title']}",
            "created_at": utc_now(),
            "source_id": source["id"],
            "capture_id": capture["id"],
            "risk_level": risk_level,
            "status": proposal_status,
            "graph_status": graph_status,
            "summary": f"Adds/updates a researched node for {source['title']} and {len(edges)} keyword-derived relation(s).",
            "review_guidance": [
                "Keyword-derived edges are provisional by default.",
                "Promote or strengthen relation names only when the source evidence supports the stronger claim.",
                "Rollback the change set if the source turns out to be weak, stale, or misleading."
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title,
              status=excluded.status,
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
                proposal_status,
                risk_level,
                str(proposal_path),
                proposal["summary"],
            ),
        )

    return proposal_path, proposal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", help="Capture id or capture metadata JSON path")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--title")
    parser.add_argument("--risk-level", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--no-keyword-edges", action="store_true")
    parser.add_argument("--graph-status", choices=["active", "provisional"], default="provisional")
    args = parser.parse_args()

    root = Path(args.root)
    proposal_path, proposal = build_graph_proposal(
        root=root,
        capture_ref=args.capture,
        title=args.title,
        risk_level=args.risk_level,
        no_keyword_edges=args.no_keyword_edges,
        graph_status=args.graph_status,
    )

    print(f"Wrote proposal: {proposal_path}")
    print(f"proposal_id: {proposal['id']}")
    print(f"nodes: {len(proposal.get('nodes', []))}")
    print(f"edges: {len(proposal.get('edges', []))}")
    print()
    print("Apply, edit first if needed:")
    print(f"  python3.12 \"{root / 'scripts' / 'apply_graph_update.py'}\" \"{proposal_path}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
