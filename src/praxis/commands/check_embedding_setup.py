#!/usr/bin/env python3
"""Check readiness for real semantic embeddings."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from vector_common import (
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VECTOR_DB,
    connect,
    embed_texts,
    ensure_schema,
    estimate_embedding_cost,
    load_env_file,
    model_id,
)


def default_dimensions(model: str) -> int:
    return 3072 if model == "text-embedding-3-large" else 1536


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_VECTOR_DB))
    parser.add_argument("--provider", choices=["openai"], default="openai")
    parser.add_argument("--model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--dimensions", type=int, default=0)
    parser.add_argument("--env-file", help="Load API credentials from a local .env file.")
    parser.add_argument("--live", action="store_true", help="Make a one-input live embedding API call.")
    args = parser.parse_args()

    if args.env_file:
        loaded = load_env_file(Path(args.env_file).expanduser())
        print(f"env_file_loaded: {loaded}")

    dimensions = args.dimensions or default_dimensions(args.model)
    identifier = model_id(args.provider, args.model, dimensions)

    with connect(Path(args.db)) as connection:
        ensure_schema(connection)
        chunk_count = connection.execute("SELECT COUNT(*) AS count FROM semantic_chunks").fetchone()["count"]
        existing = connection.execute(
            "SELECT COUNT(*) AS count FROM chunk_embeddings WHERE model_id = ?",
            (identifier,),
        ).fetchone()["count"]
        token_estimate = connection.execute(
            "SELECT COALESCE(SUM(token_estimate), 0) AS tokens FROM semantic_chunks"
        ).fetchone()["tokens"]

    key_present = bool(os.environ.get("OPENAI_API_KEY"))
    print(f"vector_db: {Path(args.db)}")
    print(f"provider: {args.provider}")
    print(f"model: {args.model}")
    print(f"dimensions: {dimensions}")
    print(f"model_id: {identifier}")
    print(f"chunks: {chunk_count}")
    print(f"existing_embeddings_for_model: {existing}")
    print(f"estimated_tokens_for_full_index: {int(token_estimate):,}")
    print(f"estimated_full_index_cost: ${estimate_embedding_cost(int(token_estimate), args.model):.6f}")
    print(f"OPENAI_API_KEY: {'set' if key_present else 'missing'}")

    if args.live:
        if not key_present:
            raise SystemExit("Cannot run --live because OPENAI_API_KEY is missing.")
        vector = embed_texts(
            ["Praxis embedding setup check."],
            provider=args.provider,
            model=args.model,
            dimensions=dimensions,
        )[0]
        print(f"live_embedding_dimensions: {len(vector)}")
        print("live_embedding_status: ok")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
