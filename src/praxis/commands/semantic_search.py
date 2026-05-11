#!/usr/bin/env python3
"""Search the semantic vector index with vector and/or full-text retrieval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vector_common import (
    DEFAULT_LOCAL_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VECTOR_DB,
    connect,
    cosine_similarity,
    embed_texts,
    ensure_schema,
    fts_query,
    load_env_file,
    model_id,
    sha256_text,
    tokenize,
    unpack_vector,
    utc_now,
)


def default_dimensions(provider: str, model: str) -> int:
    if provider == "openai" and model == "text-embedding-3-large":
        return 3072
    if provider == "openai":
        return 1536
    return 384


def default_model(provider: str) -> str:
    return DEFAULT_OPENAI_MODEL if provider == "openai" else DEFAULT_LOCAL_MODEL


def vector_hits(connection, query: str, *, provider: str, model: str, dimensions: int, limit: int) -> list[dict]:
    identifier = model_id(provider, model, dimensions)
    model_row = connection.execute("SELECT * FROM embedding_models WHERE id = ?", (identifier,)).fetchone()
    if not model_row:
        return []
    query_vector = embed_texts([query], provider=provider, model=model, dimensions=dimensions)[0]
    rows = connection.execute(
        """
        SELECT sc.*, sd.path, sd.url, sd.content_hash, ce.vector
        FROM chunk_embeddings ce
        JOIN semantic_chunks sc ON sc.id = ce.chunk_id
        JOIN semantic_documents sd ON sd.id = sc.document_id
        WHERE ce.model_id = ? AND ce.status = 'active'
        """,
        (identifier,),
    ).fetchall()
    scored = []
    for row in rows:
        score = cosine_similarity(query_vector, unpack_vector(row["vector"]))
        scored.append({"score": score, "mode": "vector", "row": row})
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]


def keyword_hits(connection, query: str, *, limit: int) -> list[dict]:
    terms = tokenize(query)
    if not terms:
        return []
    rows = connection.execute(
        """
        SELECT sc.*, sd.path, sd.url, sd.content_hash, bm25(semantic_chunks_fts) AS rank
        FROM semantic_chunks_fts
        JOIN semantic_chunks sc ON sc.id = semantic_chunks_fts.chunk_id
        JOIN semantic_documents sd ON sd.id = sc.document_id
        WHERE semantic_chunks_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (fts_query(query), limit),
    ).fetchall()
    hits = []
    for idx, row in enumerate(rows):
        # FTS rank is lower-is-better; convert rank order to a simple 0..1 score.
        score = 1.0 / (idx + 1)
        hits.append({"score": score, "mode": "keyword", "row": row})
    return hits


def print_hits(hits: list[dict], *, show_text: bool) -> None:
    if not hits:
        print("No hits.")
        return
    for idx, hit in enumerate(hits, 1):
        row = hit["row"]
        print(f"{idx}. [{hit['mode']} {hit['score']:.3f}] {row['title']}")
        print(f"   chunk_id: {row['id']}")
        if row["section"]:
            print(f"   section: {row['section']}")
        print(f"   path: {row['path']}")
        if row["url"]:
            print(f"   url: {row['url']}")
        if show_text:
            text = " ".join(row["text"].split())
            print(f"   text: {text[:700]}")
        print()


def log_retrieval(connection, query: str, mode: str, model: str, hits: list[dict]) -> None:
    try:
        connection.execute(
            """
            INSERT INTO retrieval_logs(id, query, mode, model_id, result_count, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"retrieval:{sha256_text(query + mode + utc_now())[:16]}",
                query,
                mode,
                model,
                len(hits),
                json.dumps({"top_chunk_ids": [hit["row"]["id"] for hit in hits[:10]]}, sort_keys=True),
                utc_now(),
            ),
        )
    except Exception:
        # Search should still work in read-only/sandboxed contexts.
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--db", default=str(DEFAULT_VECTOR_DB))
    parser.add_argument("--provider", choices=["local-hash", "openai"], default="local-hash")
    parser.add_argument("--model", default="")
    parser.add_argument("--dimensions", type=int, default=0)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--mode", choices=["vector", "keyword", "both"], default="both")
    parser.add_argument("--show-text", action="store_true")
    parser.add_argument("--env-file", help="Load API credentials from a local .env file without storing them in the DB.")
    args = parser.parse_args()

    if args.env_file:
        load_env_file(Path(args.env_file).expanduser())

    model = args.model or default_model(args.provider)
    dimensions = args.dimensions or default_dimensions(args.provider, model)
    with connect(Path(args.db)) as connection:
        ensure_schema(connection)
        hits: list[dict] = []
        if args.mode in {"vector", "both"}:
            hits.extend(vector_hits(connection, args.query, provider=args.provider, model=model, dimensions=dimensions, limit=args.limit))
        if args.mode in {"keyword", "both"}:
            hits.extend(keyword_hits(connection, args.query, limit=args.limit))
        hits = sorted(hits, key=lambda item: item["score"], reverse=True)[: args.limit]
        log_retrieval(connection, args.query, args.mode, model_id(args.provider, model, dimensions), hits)

    print_hits(hits, show_text=args.show_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
