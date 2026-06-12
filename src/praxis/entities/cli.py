"""CLI for entity-aware evidence retrieval."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from praxis.paths import default_root, kg_dir, vectors_dir

from .extraction import extract_mentions
from .resolution import resolve_mentions
from .retrieval import accepted_entity_links_for_chunk, annotation_payload, entity_hints_for_query
from .storage import connect_entity_db, load_graph_entities, normalize_entity_text


def active_root(args: argparse.Namespace) -> Path:
    return Path(args.root or default_root()).expanduser().resolve()


def vector_db(root: Path) -> Path:
    return vectors_dir(root) / "semantic_index.sqlite"


def graph_db(root: Path) -> Path:
    return kg_dir(root) / "skill_graph.sqlite"


def cmd_init(args: argparse.Namespace) -> int:
    root = active_root(args)
    with connect_entity_db(vector_db(root)) as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM sqlite_master WHERE type = 'table' AND name LIKE 'entity_%'").fetchone()
    print("status: ok")
    print(f"entity_tables: {row['count']}")
    print(f"vector_db: {vector_db(root)}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    root = active_root(args)
    summary = extract_mentions(
        vector_db=vector_db(root),
        kg_db=graph_db(root),
        changed_only=args.changed_only,
        include_patterns=args.include_patterns,
        limit=args.limit,
    )
    print("status: ok")
    print(f"run_id: {summary.run_id}")
    print(f"extractor: {summary.extractor}")
    print(f"chunks_scanned: {summary.chunks_scanned}")
    print(f"mentions_written: {summary.mentions_written}")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    root = active_root(args)
    summary = resolve_mentions(
        vector_db=vector_db(root),
        kg_db=graph_db(root),
        status=args.status,
        limit=args.limit,
    )
    print("status: ok")
    print(f"mentions_seen: {summary.mentions_seen}")
    print(f"accepted: {summary.accepted}")
    print(f"needs_review: {summary.needs_review}")
    print(f"unresolved: {summary.unresolved}")
    return 0


def cmd_mentions(args: argparse.Namespace) -> int:
    root = active_root(args)
    clauses = []
    params: list[object] = []
    if args.status:
        clauses.append("status = ?")
        params.append(args.status)
    if args.entity:
        clauses.append("(resolved_node_id = ? OR normalized_text LIKE ? OR surface_text LIKE ?)")
        params.extend([args.entity, f"%{normalize_entity_text(args.entity)}%", f"%{args.entity}%"])
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(args.limit)
    with connect_entity_db(vector_db(root)) as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM entity_mentions
            {where}
            ORDER BY updated_at DESC, confidence DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    if not rows:
        print("No entity mentions found.")
        return 0
    for row in rows:
        print(f"- {row['id']}")
        print(f"  surface: {row['surface_text']}")
        print(f"  normalized: {row['normalized_text']}")
        print(f"  type: {row['entity_type']}")
        print(f"  chunk_id: {row['chunk_id']}")
        print(f"  status: {row['status']}")
        print(f"  resolution_status: {row['resolution_status']}")
        if row["resolved_node_id"]:
            print(f"  resolved_node_id: {row['resolved_node_id']}")
        if row["evidence_annotation_id"]:
            print(f"  evidence_annotation_id: {row['evidence_annotation_id']}")
    return 0


def node_rows_for_query(root: Path, query: str, include_inactive: bool = False) -> list[sqlite3.Row]:
    db_path = graph_db(root)
    if not db_path.exists():
        return []
    normalized = normalize_entity_text(query)
    tokens = [token for token in normalized.split() if len(token) >= 3]
    clauses = ["lower(n.name) LIKE ?", "lower(a.alias) LIKE ?"]
    params: list[object] = [f"%{query.lower()}%", f"%{query.lower()}%"]
    for token in tokens[:8]:
        clauses.extend(["lower(n.name) LIKE ?", "lower(a.alias) LIKE ?"])
        params.extend([f"%{token}%", f"%{token}%"])
    status_clause = "" if include_inactive else "AND n.status IN ('active', 'provisional')"
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            f"""
            SELECT DISTINCT n.*
            FROM nodes n
            LEFT JOIN aliases a ON a.node_id = n.id
            WHERE ({' OR '.join(clauses)})
            {status_clause}
            ORDER BY CASE WHEN lower(n.name) = ? THEN 0 ELSE 1 END, n.name
            LIMIT 10
            """,
            (*params, query.lower()),
        ).fetchall()


def cmd_explain(args: argparse.Namespace) -> int:
    root = active_root(args)
    nodes = node_rows_for_query(root, args.entity, include_inactive=args.include_inactive)
    hints = entity_hints_for_query(vector_db(root), graph_db(root), args.entity, limit=10)
    if not nodes and hints:
        hint_ids = {hint["node_id"] for hint in hints}
        with sqlite3.connect(graph_db(root)) as connection:
            connection.row_factory = sqlite3.Row
            placeholders = ", ".join("?" for _ in hint_ids)
            nodes = connection.execute(f"SELECT * FROM nodes WHERE id IN ({placeholders})", sorted(hint_ids)).fetchall()
    if not nodes:
        print(f"No canonical entity found for: {args.entity}")
        if hints:
            print("\n## Retrieval hints")
            for hint in hints:
                print(f"- {hint['node_id']}: {hint['surface_text']} ({hint['source']})")
        return 1
    with connect_entity_db(vector_db(root)) as connection:
        for node in nodes:
            print(f"# {node['name']}")
            print(f"- node_id: {node['id']}")
            print(f"- type: {node['type']}")
            print(f"- status: {node['status']}")
            print(f"- confidence: {node['confidence']}")
            mentions = connection.execute(
                """
                SELECT em.*, sc.title, sc.section, sd.path
                FROM entity_mentions em
                JOIN semantic_chunks sc ON sc.id = em.chunk_id
                JOIN semantic_documents sd ON sd.id = sc.document_id
                WHERE em.resolved_node_id = ?
                ORDER BY em.confidence DESC, em.updated_at DESC
                LIMIT ?
                """,
                (node["id"], args.limit),
            ).fetchall()
            print(f"- resolved_mentions: {len(mentions)}")
            for mention in mentions:
                print(f"  - {mention['surface_text']} -> {mention['chunk_id']} ({mention['resolution_status']})")
                print(f"    path: {mention['path']}")
                if mention["evidence_annotation_id"]:
                    print(f"    evidence_annotation_id: {mention['evidence_annotation_id']}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    root = active_root(args)
    hints = entity_hints_for_query(vector_db(root), graph_db(root), args.query, limit=args.limit)
    print("# Entity-aware hits\n")
    if not hints:
        print("No resolved entity hints found.")
        return 0
    with connect_entity_db(vector_db(root)) as connection:
        for hint in hints:
            print(f"## {hint['surface_text']}")
            print(f"- node_id: {hint['node_id']}")
            print(f"- score: {hint['score']:.3f}")
            print(f"- source: {hint['source']}")
            rows = connection.execute(
                """
                SELECT em.*, sc.title, sc.section, sc.text, sd.path, sd.url
                FROM entity_mentions em
                JOIN semantic_chunks sc ON sc.id = em.chunk_id
                JOIN semantic_documents sd ON sd.id = sc.document_id
                WHERE em.resolved_node_id = ?
                  AND em.resolution_status = 'accepted'
                ORDER BY em.confidence DESC, em.updated_at DESC
                LIMIT ?
                """,
                (hint["node_id"], args.chunks_per_entity),
            ).fetchall()
            for row in rows:
                print(f"  - chunk_id: {row['chunk_id']}")
                print(f"    title: {row['title']}")
                print(f"    path: {row['path']}")
                if row["section"]:
                    print(f"    section: {row['section']}")
                if row["evidence_annotation_id"]:
                    print(f"    evidence_annotation_id: {row['evidence_annotation_id']}")
                if args.show_text:
                    print(f"    text: {' '.join(str(row['text']).split())[:args.text_chars]}")
    return 0


def cmd_show_annotation(args: argparse.Namespace) -> int:
    root = active_root(args)
    payload = annotation_payload(vector_db(root), args.annotation)
    if payload is None:
        print(f"Evidence annotation not found: {args.annotation}")
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Entity-aware evidence retrieval.")
    parser.add_argument("--root", default=str(default_root()), help="Praxis workspace root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Initialize entity annotation tables.")
    init.set_defaults(func=cmd_init)

    extract = subparsers.add_parser("extract", help="Extract entity mentions from semantic chunks.")
    extract.add_argument("--changed-only", action="store_true")
    extract.add_argument("--include-patterns", action="store_true", help="Also extract low-confidence capitalized phrase candidates.")
    extract.add_argument("--limit", type=int, default=0)
    extract.set_defaults(func=cmd_extract)

    resolve = subparsers.add_parser("resolve", help="Resolve mentions against SkillGraph nodes and aliases.")
    resolve.add_argument("--status", default="candidate")
    resolve.add_argument("--limit", type=int, default=0)
    resolve.set_defaults(func=cmd_resolve)

    mentions = subparsers.add_parser("mentions", help="List entity mentions.")
    mentions.add_argument("--status", default="")
    mentions.add_argument("--entity", default="")
    mentions.add_argument("--limit", type=int, default=25)
    mentions.set_defaults(func=cmd_mentions)

    explain = subparsers.add_parser("explain", help="Explain a resolved entity and its supporting mentions.")
    explain.add_argument("entity")
    explain.add_argument("--limit", type=int, default=10)
    explain.add_argument("--include-inactive", action="store_true")
    explain.set_defaults(func=cmd_explain)

    search = subparsers.add_parser("search", help="Retrieve chunks through resolved entity evidence.")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=8)
    search.add_argument("--chunks-per-entity", type=int, default=3)
    search.add_argument("--show-text", action="store_true")
    search.add_argument("--text-chars", type=int, default=700)
    search.set_defaults(func=cmd_search)

    annotation = subparsers.add_parser("annotation", help="Inspect an evidence annotation.")
    annotation.add_argument("annotation")
    annotation.set_defaults(func=cmd_show_annotation)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
