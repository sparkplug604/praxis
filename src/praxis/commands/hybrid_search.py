#!/usr/bin/env python3
"""Hybrid retrieval over vectors, keyword FTS, and SkillGraph hints."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

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


def graph_matches(kg_db: Path, query: str, limit: int) -> list[sqlite3.Row]:
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

    with sqlite3.connect(kg_db) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT DISTINCT n.*
            FROM nodes n
            LEFT JOIN aliases a ON a.node_id = n.id
            WHERE {' OR '.join(clauses)}
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


def combine_hits(vector_results: list[dict], keyword_results: list[dict], nodes: list[sqlite3.Row], weights: dict[str, float]) -> list[dict]:
    combined: dict[str, dict] = {}
    max_vector = max([hit["score"] for hit in vector_results], default=1.0) or 1.0
    max_keyword = max([hit["score"] for hit in keyword_results], default=1.0) or 1.0

    for hit in vector_results:
        chunk_id = hit["row"]["id"]
        entry = combined.setdefault(chunk_id, {"row": hit["row"], "vector": 0.0, "keyword": 0.0, "graph": 0.0})
        entry["vector"] = max(entry["vector"], hit["score"] / max_vector)

    for hit in keyword_results:
        chunk_id = hit["row"]["id"]
        entry = combined.setdefault(chunk_id, {"row": hit["row"], "vector": 0.0, "keyword": 0.0, "graph": 0.0})
        entry["keyword"] = max(entry["keyword"], hit["score"] / max_keyword)

    for entry in combined.values():
        entry["graph"] = graph_score(entry["row"], nodes)
        entry["score"] = (
            weights["vector"] * entry["vector"]
            + weights["keyword"] * entry["keyword"]
            + weights["graph"] * entry["graph"]
        )

    return sorted(combined.values(), key=lambda item: item["score"], reverse=True)


def print_results(results: list[dict], nodes: list[sqlite3.Row], *, show_text: bool, limit: int, text_chars: int) -> None:
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
            f"{idx}. [{item['score']:.3f}] {row['title']} "
            f"(v={item['vector']:.2f}, k={item['keyword']:.2f}, g={item['graph']:.2f})"
        )
        print(f"   chunk_id: {row['id']}")
        if row["section"]:
            print(f"   section: {row['section']}")
        print(f"   path: {row['path']}")
        if row["url"]:
            print(f"   url: {row['url']}")
        if show_text:
            print(f"   text: {' '.join(row['text'].split())[:text_chars]}")
        print()


def log_retrieval(connection, query: str, model_identifier: str, results: list[dict], nodes: list[sqlite3.Row]) -> None:
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
                        "graph_nodes": [node["id"] for node in nodes[:10]],
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
    parser.add_argument("--show-text", action="store_true")
    parser.add_argument("--text-chars", type=int, default=900, help="Characters of each hit to print with --show-text.")
    parser.add_argument("--env-file", help="Load API credentials from a local .env file without storing them in the DB.")
    args = parser.parse_args()

    if args.env_file:
        load_env_file(Path(args.env_file).expanduser())

    model = args.model or default_model(args.provider)
    dimensions = args.dimensions or default_dimensions(args.provider, model)
    identifier = model_id(args.provider, model, dimensions)
    nodes = graph_matches(Path(args.kg_db), args.query, args.limit)

    with connect(Path(args.db)) as connection:
        ensure_schema(connection)
        vectors = vector_hits(connection, args.query, provider=args.provider, model=model, dimensions=dimensions, limit=args.candidate_limit)
        keywords = keyword_hits(connection, args.query, limit=args.candidate_limit)
        results = combine_hits(
            vectors,
            keywords,
            nodes,
            {"vector": args.vector_weight, "keyword": args.keyword_weight, "graph": args.graph_weight},
        )
        log_retrieval(connection, args.query, identifier, results, nodes)

    print_results(results, nodes, show_text=args.show_text, limit=args.limit, text_chars=args.text_chars)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
