#!/usr/bin/env python3
"""Extract, review, promote, and query relationship evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from praxis.relationship_evidence.review import get_review_item, list_review_items, resolve_review_item
from praxis.relationship_evidence.service import RelationshipEvidenceService
from praxis.paths import default_root, vectors_dir


def vector_db_path(args: argparse.Namespace) -> Path:
    if args.vector_db:
        return Path(args.vector_db).expanduser().resolve()
    return vectors_dir(args.root) / "semantic_index.sqlite"


def service_for(args: argparse.Namespace) -> RelationshipEvidenceService:
    return RelationshipEvidenceService(vector_db=vector_db_path(args))


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def cmd_extract(args: argparse.Namespace) -> int:
    summary = service_for(args).extract_relations(changed_only=args.changed_only, limit=args.limit)
    print("# Relationship Evidence extraction\n")
    print(f"vector_db: {vector_db_path(args)}")
    print(f"chunks_scanned: {summary.chunks_scanned}")
    print(f"claims_seen: {summary.claims_seen}")
    print(f"candidates_written: {summary.candidates_written}")
    print(f"extractor: {summary.extractor}")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    summary = service_for(args).promote_candidates(
        status=args.status,
        min_confidence=args.min_confidence,
        limit=args.limit,
    )
    print("# Relationship Evidence promotion\n")
    print(f"vector_db: {vector_db_path(args)}")
    print(f"candidates_seen: {summary.candidates_seen}")
    print(f"accepted: {summary.accepted}")
    print(f"needs_review: {summary.needs_review}")
    print(f"rejected: {summary.rejected}")
    return 0


def print_review_item(item: dict[str, Any]) -> None:
    print(f"- {item['id']}")
    print(f"  object: {item['object_type']} {item['object_id']}")
    print(f"  reason: {item['reason']}")
    print(f"  status: {item['status']}")
    metadata = item.get("metadata") or {}
    if metadata.get("subject_text") or metadata.get("predicate") or metadata.get("object_value"):
        print(
            "  claim: "
            f"{metadata.get('subject_text', '')} "
            f"--{metadata.get('predicate', '')}--> "
            f"{metadata.get('object_value', '')}"
        )


def cmd_review_list(args: argparse.Namespace) -> int:
    items = list_review_items(vector_db=vector_db_path(args), status=args.status, limit=args.limit)
    if not items:
        print("No relationship evidence review items found.")
        return 0
    print("# Relationship Evidence review items\n")
    for item in items:
        print_review_item(item)
    return 0


def cmd_review_show(args: argparse.Namespace) -> int:
    item = get_review_item(vector_db=vector_db_path(args), review_id=args.review_id)
    if item is None:
        print(f"Review item not found: {args.review_id}")
        return 1
    print("# Relationship Evidence review item\n")
    print_review_item(item)
    metadata = item.get("metadata") or {}
    if metadata:
        print(f"  metadata: {json.dumps(metadata, sort_keys=True)}")
    return 0


def cmd_review_resolve(args: argparse.Namespace) -> int:
    ok = resolve_review_item(
        vector_db=vector_db_path(args),
        review_id=args.review_id,
        status=args.status,
        resolution=args.resolution,
        notes=args.notes,
    )
    if not ok:
        print(f"Review item not found: {args.review_id}")
        return 1
    print(f"Resolved relationship evidence review item: {args.review_id}")
    print(f"status: {args.status}")
    if args.resolution:
        print(f"resolution: {args.resolution}")
    return 0


def print_relationship(edge: dict[str, Any]) -> None:
    print(f"- {edge['id']}")
    print(f"  subject: {edge['subject_text'] or edge['subject_entity_id']}")
    print(f"  predicate: {edge['predicate']}")
    print(f"  object: {edge['object_value'] or edge['object_entity_id']}")
    print(f"  confidence: {edge['confidence']:.3f}")
    print(f"  status: {edge['status']}")
    if edge.get("evidence_annotation_id"):
        print(f"  evidence: {edge['evidence_annotation_id']}")
    if edge.get("chunk_id"):
        print(f"  chunk: {edge['chunk_id']}")
    if edge.get("document_path"):
        print(f"  source: {edge['document_path']}")


def cmd_query(args: argparse.Namespace) -> int:
    relationships = service_for(args).find_relationships(
        subject=args.subject,
        predicate=args.predicate,
        object_value=args.object,
        query=args.query,
        status=args.status,
        limit=args.limit,
        include_evidence=not args.no_evidence,
    )
    if args.json:
        print_json(relationships)
        return 0
    if not relationships:
        print("No accepted graph relationships found.")
        return 0
    print("# Graph relationships\n")
    for edge in relationships:
        print_relationship(edge)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    result = service_for(args).compare_entities(args.left, args.right, limit=args.limit)
    if args.json:
        print_json(result)
        return 0
    print("# Entity relationship comparison\n")
    print(f"left: {result['left']}")
    print(f"right: {result['right']}")
    print(f"left_edges: {len(result['left_edges'])}")
    print(f"right_edges: {len(result['right_edges'])}")
    print(f"shared_relationships: {len(result['shared_relationships'])}")
    for item in result["shared_relationships"]:
        print(f"- {item['predicate']}: {item['object_value']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(default_root()), help="Praxis root")
    parser.add_argument("--vector-db", default="", help="Override semantic index SQLite path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract", help="Extract relationship candidates from semantic chunks.")
    extract.add_argument("--changed-only", action="store_true", help="Scan chunks not previously processed by entity extraction.")
    extract.add_argument("--limit", type=int, default=0, help="Limit chunks scanned.")
    extract.set_defaults(func=cmd_extract)

    promote = subparsers.add_parser("promote", help="Promote safe relationship candidates into accepted graph edges.")
    promote.add_argument("--status", default="candidate", help="Candidate status to promote from.")
    promote.add_argument("--min-confidence", type=float, default=0.70)
    promote.add_argument("--limit", type=int, default=0)
    promote.set_defaults(func=cmd_promote)

    review = subparsers.add_parser("review", help="List, inspect, or resolve relationship evidence review items.")
    review_sub = review.add_subparsers(dest="review_command", required=True)

    review_list = review_sub.add_parser("list", help="List relationship evidence review items.")
    review_list.add_argument("--status", default="open", help="Filter by status. Use empty string for all statuses.")
    review_list.add_argument("--limit", type=int, default=25)
    review_list.set_defaults(func=cmd_review_list)

    review_show = review_sub.add_parser("show", help="Show one relationship evidence review item.")
    review_show.add_argument("review_id")
    review_show.set_defaults(func=cmd_review_show)

    review_resolve = review_sub.add_parser("resolve", help="Resolve, acknowledge, or suppress one review item.")
    review_resolve.add_argument("review_id")
    review_resolve.add_argument("--status", choices=["resolved", "acknowledged", "suppressed", "false_positive"], default="resolved")
    review_resolve.add_argument("--resolution", default="")
    review_resolve.add_argument("--notes", default="")
    review_resolve.set_defaults(func=cmd_review_resolve)

    query = subparsers.add_parser("query", help="Query accepted graph relationships.")
    query.add_argument("--subject", default="")
    query.add_argument("--predicate", default="")
    query.add_argument("--object", default="")
    query.add_argument("--query", default="", help="Token query across subjects, predicates, and objects.")
    query.add_argument("--status", default="accepted")
    query.add_argument("--limit", type=int, default=20)
    query.add_argument("--no-evidence", action="store_true")
    query.add_argument("--json", action="store_true")
    query.set_defaults(func=cmd_query)

    compare = subparsers.add_parser("compare", help="Compare accepted relationships for two entities.")
    compare.add_argument("left")
    compare.add_argument("right")
    compare.add_argument("--limit", type=int, default=50)
    compare.add_argument("--json", action="store_true")
    compare.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
