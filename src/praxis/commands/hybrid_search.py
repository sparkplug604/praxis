#!/usr/bin/env python3
"""Hybrid retrieval over vectors, keyword FTS, and SkillGraph hints."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path

from praxis.context_priority import score_context_priority
from praxis.entities.retrieval import accepted_entity_links_for_chunk, entity_hints_for_query, entity_scores_for_chunks
from praxis.governance.policy import search_result_governance_warnings

from conflict_ledger import open_conflicts_for_objects
from graph_audit import LIVE_STATUSES
from semantic_search import default_dimensions, keyword_hits, vector_hits
from vector_common import (
    DEFAULT_KG_DB,
    DEFAULT_LOCAL_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VECTOR_DB,
    connect,
    ensure_schema,
    load_env_file,
    model_id,
    sha256_text,
    tokenize,
    utc_now,
)


def graph_matches(kg_db: Path, query: str, limit: int, *, include_inactive: bool = False) -> list[sqlite3.Row]:
    if not kg_db.exists():
        return []
    like = f"%{query}%"
    tokens = tokenize(query)
    token_likes = [f"%{token}%" for token in tokens[:8]]
    clauses = ["n.name LIKE ?", "n.summary LIKE ?", "a.alias LIKE ?"]
    params: list[object] = [like, like, like]
    for token_like in token_likes:
        clauses.extend(["n.name LIKE ?", "n.summary LIKE ?", "a.alias LIKE ?"])
        params.extend([token_like, token_like, token_like])
    graph_candidate_limit = max(limit * 10, 50)
    params.append(graph_candidate_limit)
    status_clause = ""
    if not include_inactive:
        status_clause = f"AND n.status IN ({', '.join(repr(status) for status in LIVE_STATUSES)})"

    with sqlite3.connect(kg_db) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT DISTINCT n.*
            FROM nodes n
            LEFT JOIN aliases a ON a.node_id = n.id
            WHERE ({' OR '.join(clauses)})
            {status_clause}
            LIMIT ?
            """,
            params,
        ).fetchall()
    query_lower = query.lower()
    tokens = tokenize(query)

    def score(row: sqlite3.Row) -> float:
        name = row["name"].lower()
        node_id = row["id"].lower()
        summary = row["summary"].lower()
        haystack = f"{node_id} {name} {summary}"
        value = 0.0
        if query_lower in name or query_lower in node_id:
            value += 8.0
        value += sum(2.0 for token in tokens if token in name or token in node_id)
        value += sum(0.5 for token in tokens if token in summary)
        if row["type"] in {"runtime", "tool", "concept", "failure_mode"}:
            value += 0.4
        return value

    return sorted(rows, key=lambda row: (-score(row), row["type"], row["name"]))[:limit]


def default_model(provider: str) -> str:
    return DEFAULT_OPENAI_MODEL if provider == "openai" else DEFAULT_LOCAL_MODEL


def graph_score(row, nodes: list[sqlite3.Row]) -> float:
    if not nodes:
        return 0.0
    text = f"{row['title']} {row['section']} {row['text'][:2500]}".lower()
    try:
        linked = set(json.loads(row["graph_node_ids_json"] or "[]"))
    except json.JSONDecodeError:
        linked = set()
    score = 0.0
    for node in nodes:
        node_id = node["id"]
        node_name = node["name"].lower()
        if node_id in linked:
            score += 1.0
        elif node_name and node_name in text:
            score += 0.6
        else:
            node_tokens = tokenize(node_name)
            if node_tokens and any(token in text for token in node_tokens):
                score += 0.2
    return min(score, 2.0) / 2.0


def chunk_graph_links(row: sqlite3.Row) -> list[str]:
    try:
        value = json.loads(row["graph_node_ids_json"] or "[]")
    except (KeyError, json.JSONDecodeError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def chunk_metadata(row: sqlite3.Row) -> dict:
    try:
        value = json.loads(row["metadata_json"] or "{}")
    except (KeyError, json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def combine_hits(
    vector_results: list[dict],
    keyword_results: list[dict],
    nodes: list[sqlite3.Row],
    weights: dict[str, float],
    entity_scores: Mapping[str, float] | None = None,
) -> list[dict]:
    combined: dict[str, dict] = {}
    max_vector = max([hit["score"] for hit in vector_results], default=1.0) or 1.0
    max_keyword = max([hit["score"] for hit in keyword_results], default=1.0) or 1.0

    for hit in vector_results:
        chunk_id = hit["row"]["id"]
        entry = combined.setdefault(chunk_id, {"row": hit["row"], "vector": 0.0, "keyword": 0.0, "graph": 0.0, "entity": 0.0})
        entry["vector"] = max(entry["vector"], hit["score"] / max_vector)

    for hit in keyword_results:
        chunk_id = hit["row"]["id"]
        entry = combined.setdefault(chunk_id, {"row": hit["row"], "vector": 0.0, "keyword": 0.0, "graph": 0.0, "entity": 0.0})
        entry["keyword"] = max(entry["keyword"], hit["score"] / max_keyword)

    for entry in combined.values():
        chunk_id = entry["row"]["id"]
        entry["graph"] = graph_score(entry["row"], nodes)
        entry["entity"] = float((entity_scores or {}).get(chunk_id, 0.0))
        entry["relevance"] = (
            weights["vector"] * entry["vector"]
            + weights["keyword"] * entry["keyword"]
            + weights["graph"] * entry["graph"]
            + weights.get("entity", 0.0) * entry["entity"]
        )
        entry["score"] = entry["relevance"]
        entry["priority"] = entry["relevance"]

    return sorted(combined.values(), key=lambda item: item["relevance"], reverse=True)


def conflict_refs_for_result(row: sqlite3.Row, nodes: list[sqlite3.Row]) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    if row["source_id"]:
        refs.append(("source", row["source_id"]))
    if row["capture_id"]:
        refs.append(("capture", row["capture_id"]))
    refs.extend(("node", node_id) for node_id in chunk_graph_links(row))
    refs.extend(("node", node["id"]) for node in nodes[:8])
    return refs


def source_context_for_result(connection: sqlite3.Connection, row: sqlite3.Row) -> sqlite3.Row | None:
    if not row["source_id"]:
        return None
    return connection.execute(
        """
        SELECT *
        FROM source_registry
        WHERE id = ?
        """,
        (row["source_id"],),
    ).fetchone()


def annotate_context_priority(
    results: list[dict],
    nodes: list[sqlite3.Row],
    *,
    kg_db: Path,
    rank_by: str,
) -> list[dict]:
    if kg_db.exists():
        try:
            with sqlite3.connect(kg_db) as connection:
                connection.row_factory = sqlite3.Row
                for item in results:
                    row = item["row"]
                    refs = conflict_refs_for_result(row, nodes)
                    conflicts = open_conflicts_for_objects(connection, refs)
                    source = source_context_for_result(connection, row)
                    breakdown = score_context_priority(
                        relevance=float(item["relevance"]),
                        row=row,
                        source=source,
                        graph=float(item["graph"]),
                        conflicts=conflicts,
                    )
                    item["priority"] = breakdown.priority
                    item["priority_breakdown"] = breakdown.to_dict()
                    item["conflicts"] = conflicts
        except sqlite3.Error:
            pass

    for item in results:
        if "priority_breakdown" not in item:
            breakdown = score_context_priority(
                relevance=float(item["relevance"]),
                row=item["row"],
                graph=float(item["graph"]),
                conflicts=[],
            )
            item["priority"] = breakdown.priority
            item["priority_breakdown"] = breakdown.to_dict()
            item["conflicts"] = []
        item["score"] = item["priority"] if rank_by == "priority" else item["relevance"]

    return sorted(results, key=lambda item: item["score"], reverse=True)


def print_explanation(item: dict, nodes: list[sqlite3.Row]) -> None:
    row = item["row"]
    print(
        "   explain: "
        f"priority={item['priority']:.3f}; "
        f"relevance={item['relevance']:.3f}; "
        f"vector={item['vector']:.3f}; "
        f"keyword={item['keyword']:.3f}; "
        f"graph={item['graph']:.3f}; "
        f"entity={item.get('entity', 0.0):.3f}"
    )
    breakdown = item.get("priority_breakdown") or {}
    if breakdown:
        print(
            "   priority_breakdown: "
            f"trust={breakdown.get('trust', 0.0):.3f}; "
            f"freshness={breakdown.get('freshness', 0.0):.3f}; "
            f"status={breakdown.get('status', 0.0):.3f}; "
            f"conflict_penalty={breakdown.get('conflict_penalty', 0.0):.3f}"
        )
        reasons = breakdown.get("reasons") or []
        if reasons:
            print(f"   priority_reasons: {'; '.join(str(reason) for reason in reasons)}")
    if row["source_id"]:
        print(f"   source_id: {row['source_id']}")
    if row["capture_id"]:
        print(f"   capture_id: {row['capture_id']}")
    if row["confidence"]:
        print(f"   confidence: {row['confidence']}")
    metadata = chunk_metadata(row)
    intake = metadata.get("intake") if isinstance(metadata.get("intake"), dict) else {}
    if intake:
        parse_quality = intake.get("parse_quality") if isinstance(intake.get("parse_quality"), dict) else {}
        score = parse_quality.get("score")
        converter = intake.get("converter_name") or ""
        media_type = intake.get("media_type") or ""
        print(f"   intake: converter={converter}; media_type={media_type}; parse_quality={score}")
        warnings = intake.get("warnings") or parse_quality.get("warnings") or []
        if warnings:
            print(f"   intake_warnings: {'; '.join(str(warning) for warning in warnings[:5])}")
    links = chunk_graph_links(row)
    if links:
        print(f"   graph_links: {', '.join(links[:8])}")
    entity_links = item.get("entity_links") or []
    if entity_links:
        print("   entity_links:")
        for link in entity_links[:8]:
            print(
                "   - "
                f"{link.get('resolved_node_id')} ({link.get('entity_type')}): {link.get('surface_text')} evidence={link.get('evidence_annotation_id') or '-'}"
            )
    governance_warnings = search_result_governance_warnings(row)
    if governance_warnings:
        print("   governance_warnings:")
        for warning in governance_warnings:
            print(f"   - {warning}")
    if nodes:
        hints = ", ".join(node["id"] for node in nodes[:8])
        print(f"   graph_hints_used: {hints}")


def conflict_warnings_for_result(kg_db: Path, row: sqlite3.Row, nodes: list[sqlite3.Row]) -> list[sqlite3.Row]:
    if not kg_db.exists():
        return []
    refs = conflict_refs_for_result(row, nodes)
    try:
        with sqlite3.connect(kg_db) as connection:
            connection.row_factory = sqlite3.Row
            return open_conflicts_for_objects(connection, refs)
    except sqlite3.Error:
        return []


def result_log_payload(item: dict) -> dict:
    row = item["row"]
    return {
        "chunk_id": row["id"],
        "source_id": row["source_id"],
        "capture_id": row["capture_id"],
        "score": round(float(item["score"]), 6),
        "priority": round(float(item["priority"]), 6),
        "relevance": round(float(item["relevance"]), 6),
        "vector": round(float(item["vector"]), 6),
        "keyword": round(float(item["keyword"]), 6),
        "graph": round(float(item["graph"]), 6),
        "entity": round(float(item.get("entity", 0.0)), 6),
        "entity_links": item.get("entity_links", []),
        "conflict_count": len(item.get("conflicts", [])),
        "priority_breakdown": item.get("priority_breakdown", {}),
        "graph_links": chunk_graph_links(row),
    }


def print_results(
    results: list[dict],
    nodes: list[sqlite3.Row],
    *,
    kg_db: Path,
    show_text: bool,
    limit: int,
    text_chars: int,
    explain: bool,
) -> None:
    if nodes:
        print("# SkillGraph Hints\n")
        for node in nodes[:8]:
            print(f"- `{node['id']}` ({node['type']}): {node['name']}")
        print()

    print("# Hybrid Hits\n")
    if not results:
        print("No hits.")
        return
    for idx, item in enumerate(results[:limit], 1):
        row = item["row"]
        print(
            f"{idx}. [p={item['priority']:.3f} r={item['relevance']:.3f}] {row['title']} "
            f"(v={item['vector']:.2f}, k={item['keyword']:.2f}, "
            f"g={item['graph']:.2f}, e={item.get('entity', 0.0):.2f})"
        )
        print(f"   chunk_id: {row['id']}")
        if row["section"]:
            print(f"   section: {row['section']}")
        print(f"   path: {row['path']}")
        if row["url"]:
            print(f"   url: {row['url']}")
        if explain:
            print_explanation(item, nodes)
            conflicts = item.get("conflicts") or conflict_warnings_for_result(kg_db, row, nodes)
            if conflicts:
                print("   conflict_warnings:")
                for conflict in conflicts:
                    print(
                        "   - "
                        f"{conflict['id']} "
                        f"({conflict['conflict_type']}, {conflict['severity']}, {conflict['status']}): "
                        f"{conflict['summary']}"
                    )
        if show_text:
            print(f"   text: {' '.join(row['text'].split())[:text_chars]}")
        print()


def log_retrieval(
    connection,
    query: str,
    model_identifier: str,
    results: list[dict],
    nodes: list[sqlite3.Row],
    weights: dict[str, float],
) -> None:
    try:
        connection.execute(
            """
            INSERT INTO retrieval_logs(id, query, mode, model_id, result_count, metadata_json, created_at)
            VALUES (?, ?, 'hybrid', ?, ?, ?, ?)
            """,
            (
                f"retrieval:{sha256_text(query + 'hybrid' + utc_now())[:16]}",
                query,
                model_identifier,
                len(results),
                json.dumps(
                    {
                        "top_chunk_ids": [item["row"]["id"] for item in results[:10]],
                        "top_results": [result_log_payload(item) for item in results[:10]],
                        "graph_nodes": [node["id"] for node in nodes[:10]],
                        "weights": weights,
                    },
                    sort_keys=True,
                ),
                utc_now(),
            ),
        )
    except Exception:
        # Retrieval should still work when the vector DB is read-only.
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--db", default=str(DEFAULT_VECTOR_DB))
    parser.add_argument("--kg-db", default=str(DEFAULT_KG_DB))
    parser.add_argument("--provider", choices=["local-hash", "openai"], default="local-hash")
    parser.add_argument("--model", default="")
    parser.add_argument("--dimensions", type=int, default=0)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--candidate-limit", type=int, default=40)
    parser.add_argument("--vector-weight", type=float, default=0.45)
    parser.add_argument("--keyword-weight", type=float, default=0.45)
    parser.add_argument("--graph-weight", type=float, default=0.10)
    parser.add_argument("--entity-aware", action="store_true", help="Use resolved entity mentions as an additional retrieval signal.")
    parser.add_argument("--entity-weight", type=float, default=0.15)
    parser.add_argument(
        "--rank-by",
        choices=["priority", "relevance"],
        default="priority",
        help="Sort by unified context priority or raw retrieval relevance.",
    )
    parser.add_argument("--show-text", action="store_true")
    parser.add_argument("--explain", action="store_true", help="Print score components, source ids, and graph hints for each result.")
    parser.add_argument("--text-chars", type=int, default=900, help="Characters of each hit to print with --show-text.")
    parser.add_argument("--include-inactive-graph", action="store_true", help="Include deprecated/reverted SkillGraph hints.")
    parser.add_argument("--env-file", help="Load API credentials from a local .env file without storing them in the DB.")
    args = parser.parse_args()

    if args.env_file:
        load_env_file(Path(args.env_file).expanduser())

    model = args.model or default_model(args.provider)
    dimensions = args.dimensions or default_dimensions(args.provider, model)
    identifier = model_id(args.provider, model, dimensions)
    nodes = graph_matches(Path(args.kg_db), args.query, args.limit, include_inactive=args.include_inactive_graph)

    with connect(Path(args.db)) as connection:
        ensure_schema(connection)
        vectors = vector_hits(connection, args.query, provider=args.provider, model=model, dimensions=dimensions, limit=args.candidate_limit)
        keywords = keyword_hits(connection, args.query, limit=args.candidate_limit)
        weights = {"vector": args.vector_weight, "keyword": args.keyword_weight, "graph": args.graph_weight}
        entity_scores: dict[str, float] = {}
        if args.entity_aware:
            hints = entity_hints_for_query(Path(args.db), Path(args.kg_db), args.query, limit=args.limit)
            candidate_chunk_ids = sorted({hit["row"]["id"] for hit in [*vectors, *keywords]})
            entity_scores = entity_scores_for_chunks(Path(args.db), candidate_chunk_ids, hints)
            weights["entity"] = args.entity_weight
        results = combine_hits(
            vectors,
            keywords,
            nodes,
            weights,
            entity_scores=entity_scores,
        )
        if args.entity_aware:
            for item in results:
                item["entity_links"] = accepted_entity_links_for_chunk(Path(args.db), item["row"]["id"])
        results = annotate_context_priority(results, nodes, kg_db=Path(args.kg_db), rank_by=args.rank_by)
        log_retrieval(connection, args.query, identifier, results, nodes, weights)

    print_results(
        results,
        nodes,
        kg_db=Path(args.kg_db),
        show_text=args.show_text,
        limit=args.limit,
        text_chars=args.text_chars,
        explain=args.explain,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
