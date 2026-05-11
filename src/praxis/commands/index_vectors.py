#!/usr/bin/env python3
"""Embed semantic chunks into the local vector index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vector_common import (
    DEFAULT_LOCAL_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VECTOR_DB,
    connect,
    embed_texts,
    ensure_schema,
    estimate_embedding_cost,
    load_env_file,
    pack_vector,
    upsert_embedding_model,
    vector_hash,
    vector_norm,
)


def default_model(provider: str) -> str:
    if provider == "openai":
        return DEFAULT_OPENAI_MODEL
    return DEFAULT_LOCAL_MODEL


def default_dimensions(provider: str, model: str) -> int:
    if provider == "openai" and model == "text-embedding-3-large":
        return 3072
    if provider == "openai":
        return 1536
    return 384


def pending_chunks(connection, model_id: str, *, force: bool, limit: int) -> list:
    where = ""
    params: list[object] = []
    if not force:
        where = """
        WHERE NOT EXISTS (
          SELECT 1 FROM chunk_embeddings ce
          WHERE ce.chunk_id = sc.id AND ce.model_id = ?
        )
        """
        params.append(model_id)
    params.append(limit)
    return connection.execute(
        f"""
        SELECT sc.*
        FROM semantic_chunks sc
        {where}
        ORDER BY sc.document_id, sc.chunk_index
        LIMIT ?
        """,
        params,
    ).fetchall()


def print_estimate(rows: list, provider: str, model: str) -> None:
    tokens = sum(int(row["token_estimate"] or 0) for row in rows)
    print(f"Pending chunks: {len(rows)}")
    print(f"Estimated tokens: {tokens:,}")
    if provider == "openai":
        print(f"Estimated embedding cost: ${estimate_embedding_cost(tokens, model):.6f}")


def batches(rows: list, batch_size: int):
    for idx in range(0, len(rows), batch_size):
        yield rows[idx : idx + batch_size]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_VECTOR_DB))
    parser.add_argument("--provider", choices=["local-hash", "openai"], default="local-hash")
    parser.add_argument("--model", default="")
    parser.add_argument("--dimensions", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--force", action="store_true", help="Recompute embeddings that already exist for this model.")
    parser.add_argument("--env-file", help="Load API credentials from a local .env file without storing them in the DB.")
    parser.add_argument("--estimate-only", action="store_true", help="Print pending chunk/token/cost estimate without embedding.")
    args = parser.parse_args()

    if args.env_file:
        load_env_file(Path(args.env_file).expanduser())

    model = args.model or default_model(args.provider)
    dimensions = args.dimensions or default_dimensions(args.provider, model)

    with connect(Path(args.db)) as connection:
        ensure_schema(connection)
        model_id = upsert_embedding_model(
            connection,
            provider=args.provider,
            model=model,
            dimensions=dimensions,
            config={"batch_size": args.batch_size},
        )
        rows = pending_chunks(connection, model_id, force=args.force, limit=args.limit)
        print_estimate(rows, args.provider, model)
        if args.estimate_only:
            print(f"model_id: {model_id}")
            return 0
        if not rows:
            print("No chunks need embeddings.")
            print(f"model_id: {model_id}")
            return 0

        embedded_count = 0
        for batch in batches(rows, max(1, args.batch_size)):
            texts = [row["text"] for row in batch]
            vectors = embed_texts(texts, provider=args.provider, model=model, dimensions=dimensions)
            for row, vector in zip(batch, vectors):
                if len(vector) != dimensions:
                    raise RuntimeError(f"Expected {dimensions} dimensions, got {len(vector)} for {row['id']}")
                connection.execute(
                    """
                    INSERT INTO chunk_embeddings(
                      chunk_id, model_id, vector, vector_hash, norm, dimensions, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id, model_id) DO UPDATE SET
                      vector=excluded.vector,
                      vector_hash=excluded.vector_hash,
                      norm=excluded.norm,
                      dimensions=excluded.dimensions,
                      embedded_at=CURRENT_TIMESTAMP,
                      status='active',
                      metadata_json=excluded.metadata_json
                    """,
                    (
                        row["id"],
                        model_id,
                        pack_vector(vector),
                        vector_hash(vector),
                        vector_norm(vector),
                        dimensions,
                        json.dumps({"provider": args.provider, "model": model}, sort_keys=True),
                    ),
                )
                embedded_count += 1

    print(f"Embedded chunks: {embedded_count}")
    print(f"model_id: {model_id}")
    print(f"Vector DB: {Path(args.db)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
