#!/usr/bin/env python3
"""Healthcheck a Praxis checkout."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from praxis.paths import (
    active_runtime_paths,
    bootstrap_path,
    db_dir,
    default_root,
    kg_dir,
    legacy_runtime_paths,
    vectors_dir,
    workspace_root,
)


ROOT = default_root()
VECTOR_DB = vectors_dir(ROOT) / "semantic_index.sqlite"
KG_DB = kg_dir(ROOT) / "skill_graph.sqlite"
RELATIONAL_DB = db_dir(ROOT) / "praxis.sqlite"


def check_path(label: str, path: Path, *, required: bool = True) -> bool:
    ok = path.exists()
    status = "ok" if ok else ("missing" if required else "optional-missing")
    print(f"{status}: {label}: {path}")
    return ok or not required


def sqlite_count(db_path: Path, table: str) -> int | None:
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return None


def check_sqlite_tables(db_path: Path, tables: list[str], *, required: bool) -> bool:
    ok = check_path(db_path.name, db_path, required=required)
    if not db_path.exists():
        return ok
    for table in tables:
        count = sqlite_count(db_path, table)
        if count is None:
            status = "missing" if required else "optional-missing"
            print(f"{status}: {db_path.name} table count: {table}")
            ok = False if required else ok
        else:
            print(f"ok: {db_path.name} table {table}: {count}")
    return ok


def check_vector_completeness() -> bool:
    if not VECTOR_DB.exists():
        return True
    with sqlite3.connect(VECTOR_DB) as connection:
        chunks = int(connection.execute("SELECT COUNT(*) FROM semantic_chunks").fetchone()[0])
        embeddings = int(connection.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0])
    if chunks and not embeddings:
        print("missing: semantic chunks exist but no embeddings are present")
        return False
    return True


def check_layout() -> None:
    print(f"ok: workspace root: {workspace_root(ROOT)}")
    active = active_runtime_paths(ROOT)
    for name, legacy in legacy_runtime_paths(ROOT).items():
        active_path = active[name]
        if legacy.exists() and active_path != legacy:
            print(f"warning: legacy runtime path still exists: {legacy}")
            print("warning: run `praxis migrate-workspace --plan` to review workspace migration.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-index", action="store_true", help="Fail if generated SQLite indexes have not been initialized.")
    args = parser.parse_args()

    ok = True
    print("# Praxis doctor")
    for rel in [
        "README.md",
        "docs/README.md",
        "docs/cli.md",
        "docs/getting-started.md",
        "docs/troubleshooting.md",
        "docs/evaluators/agency-gtm-evaluation.md",
        "docs/tutorials/core-first-source.md",
        "docs/tutorials/reach-fixture-demo.md",
        "docs/tutorials/agency-fixture-demo.md",
        "scripts/demo.py",
        "scripts/setup.py",
        "scripts/research_source.py",
        "scripts/ingest_source.py",
        "scripts/chunk_sources.py",
        "scripts/index_vectors.py",
        "scripts/hybrid_search.py",
        "scripts/conflicts.py",
        "scripts/dedupe.py",
        "scripts/reach.py",
        "scripts/agency.py",
        "scripts/graph_changes.py",
        "scripts/rollback_graph_change.py",
        "scripts/promote_graph_change.py",
        "scripts/deprecate_graph_change.py",
        "adapters/README.md",
        "docs/modules/core/README.md",
        "docs/modules/reach/README.md",
        "docs/modules/reach-for-agencies/README.md",
        "docs/connectors/hubspot.md",
        "docs/connectors/google-ads.md",
        "docs/connectors/google-analytics.md",
        "docs/connectors/bigquery.md",
    ]:
        ok &= check_path(rel, ROOT / rel)

    for rel in [
        "db/schema.sql",
        "kg/schema.sql",
        "kg/seed_graph.json",
        "sources/seed_sources.json",
    ]:
        ok &= check_path(f"bootstrap/{rel}", bootstrap_path(ROOT, rel))
    check_layout()

    ok &= check_sqlite_tables(
        RELATIONAL_DB,
        ["sources", "patterns", "failure_modes", "benchmarks", "agent_practices"],
        required=args.require_index,
    )
    ok &= check_sqlite_tables(
        KG_DB,
        [
            "nodes",
            "edges",
            "source_registry",
            "source_captures",
            "graph_update_proposals",
            "graph_change_sets",
            "graph_change_items",
            "claim_records",
            "conflict_records",
            "conflict_items",
        ],
        required=args.require_index,
    )
    ok &= check_sqlite_tables(
        VECTOR_DB,
        ["semantic_documents", "semantic_chunks", "chunk_embeddings"],
        required=args.require_index,
    )
    ok &= check_vector_completeness()

    print(f"status: {'ok' if ok else 'needs-attention'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
