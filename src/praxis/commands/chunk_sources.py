#!/usr/bin/env python3
"""Chunk Praxis sources into the semantic vector index."""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
from typing import Any

from vector_common import (
    DEFAULT_ROOT,
    DEFAULT_VECTOR_DB,
    chunk_text,
    connect,
    ensure_schema,
    estimate_tokens,
    normalize_space,
    normalize_structured_text,
    read_json,
    sha256_text,
    slug,
    utc_now,
)
from praxis.paths import bootstrap_path, exports_dir, notes_dir, research_dir, sources_dir, watchlists_dir


SKILL_PATHS: list[Path] = []
RUNTIME_MANIFEST = bootstrap_path(DEFAULT_ROOT, "sources", "runtime_corpus.example.json")


def safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def is_within_excluded_dir(path: Path, excluded_dirs: set[str]) -> bool:
    return any(part in excluded_dirs for part in path.parts)


def matches_any(path: Path, root: Path, patterns: list[str]) -> bool:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.as_posix(), pattern) for pattern in patterns)


def runtime_files(manifest_path: Path = RUNTIME_MANIFEST) -> list[Path]:
    if not manifest_path.exists():
        return []
    manifest = read_json(manifest_path)
    allowed_suffixes = {suffix.lower() for suffix in manifest.get("allowed_suffixes", [])}
    global_exclude_dirs = set(manifest.get("global_exclude_dirs", []))
    global_exclude_globs = list(manifest.get("global_exclude_globs", []))
    max_file_bytes = int(manifest.get("max_file_bytes", 250000))

    paths: list[Path] = []
    for entry in manifest.get("entries", []):
        runtime_root = Path(entry["root"]).expanduser()
        if not runtime_root.exists():
            continue
        entry_exclude = list(entry.get("exclude", []))
        for pattern in entry.get("include", []):
            for path in sorted(runtime_root.glob(pattern)):
                if not path.is_file():
                    continue
                if allowed_suffixes and path.suffix.lower() not in allowed_suffixes:
                    continue
                if is_within_excluded_dir(path, global_exclude_dirs):
                    continue
                if matches_any(path, runtime_root, global_exclude_globs + entry_exclude):
                    continue
                try:
                    if path.stat().st_size > max_file_bytes:
                        continue
                except OSError:
                    continue
                paths.append(path)
    return paths


def default_files(root: Path, *, include_skills: bool, include_runtimes: bool) -> list[Path]:
    paths: list[Path] = []
    paths.extend(sorted((research_dir(root) / "captures").glob("**/*.raw.txt")))
    paths.extend(sorted((research_dir(root) / "captures").glob("**/*.summary.md")))
    paths.extend(sorted(exports_dir(root).glob("*.md")))
    paths.extend(sorted(notes_dir(root).glob("*.md")))
    paths.extend(sorted(sources_dir(root).glob("*.json")))
    paths.extend(sorted(watchlists_dir(root).glob("*.json")))
    research_readme = research_dir(root) / "README.md"
    if research_readme.exists():
        paths.append(research_readme)

    if include_skills:
        for skill_root in SKILL_PATHS:
            if not skill_root.exists():
                continue
            paths.extend(sorted(skill_root.glob("SKILL.md")))
            paths.extend(sorted((skill_root / "references").glob("*.md")) if (skill_root / "references").exists() else [])

    if include_runtimes:
        paths.extend(runtime_files())

    unique: dict[str, Path] = {}
    allowed_suffixes = {".md", ".txt", ".json", ".py", ".yaml", ".yml", ".toml"}
    for path in paths:
        if path.exists() and path.is_file() and path.suffix.lower() in allowed_suffixes:
            unique[str(path)] = path
    return list(unique.values())


def metadata_for_capture_file(path: Path) -> dict[str, Any]:
    candidates = []
    name = path.name
    if name.endswith(".raw.txt"):
        candidates.append(path.with_name(name.removesuffix(".raw.txt") + ".metadata.json"))
    if name.endswith(".summary.md"):
        candidates.append(path.with_name(name.removesuffix(".summary.md") + ".metadata.json"))
    candidates.append(path.with_suffix(".metadata.json"))

    for candidate in candidates:
        if candidate.exists():
            try:
                return read_json(candidate)
            except json.JSONDecodeError:
                return {}
    return {}


def title_from_path(path: Path, text: str, root: Path) -> str:
    for line in text.splitlines()[:60]:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("#").strip()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def source_type_for(path: Path, metadata: dict[str, Any]) -> str:
    if metadata.get("source_type"):
        return str(metadata["source_type"])
    if "/research/captures/" in str(path):
        return "capture"
    if "/exports/" in str(path):
        return "export"
    if "/watchlists/" in str(path):
        return "watchlist"
    if "/skills/" in str(path):
        return "skill"
    if "/runtimes/" in str(path):
        return "runtime"
    return "local"


def confidence_for(metadata: dict[str, Any]) -> str:
    intake = metadata.get("intake") if isinstance(metadata.get("intake"), dict) else {}
    parse_quality = intake.get("parse_quality") if isinstance(intake.get("parse_quality"), dict) else {}
    score = parse_quality.get("score")
    if isinstance(score, (int, float)):
        if score >= 0.75:
            return "high"
        if score < 0.35:
            return "low"
    score = metadata.get("credibility_score")
    if isinstance(score, int):
        if score >= 4:
            return "medium"
        if score >= 2:
            return "low"
    return "medium"


def infer_graph_nodes(path: Path, title: str, text: str) -> list[str]:
    haystack = f"{path} {title} {text[:2000]}".lower()
    candidates = {
        "concept:rag": ["rag", "retrieval augmented", "retrieval-augmented"],
        "concept:skill": ["skill", "skill.md", "agent skill"],
        "concept:knowledge-graph": ["knowledge graph", "skillgraph"],
        "concept:context-distillation": ["context distillation"],
        "concept:task-semantic-contract": ["semantic contract", "task contract"],
        "concept:divergence-detection": ["divergence", "drift"],
        "concept:side-effect-boundary": ["side effect", "side-effect"],
        "concept:quorum-governance": ["quorum"],
        "concept:deterministic-replay": ["replay", "deterministic"],
    }
    matches = []
    for node_id, needles in candidates.items():
        if any(needle in haystack for needle in needles):
            matches.append(node_id)
    return matches


def document_record(path: Path, root: Path) -> tuple[dict[str, Any], str]:
    text = safe_read(path)
    normalized = normalize_space(text)
    structured_text = normalize_structured_text(text)
    metadata = metadata_for_capture_file(path)
    content_hash = sha256_text(normalized)
    title = metadata.get("title") or title_from_path(path, normalized, root)
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = path.name
    source_id = metadata.get("source_id") or f"local:{slug(rel)}"
    capture_id = metadata.get("capture_id") or ""
    source_type = source_type_for(path, metadata)
    document_id = f"doc:{slug(rel)}:{sha256_text(rel)[:10]}"
    return (
        {
            "id": document_id,
            "source_id": source_id,
            "capture_id": capture_id,
            "title": str(title),
            "path": rel,
            "url": metadata.get("source", "") if isinstance(metadata.get("source"), str) and str(metadata.get("source")).startswith(("http://", "https://")) else "",
            "source_type": source_type,
            "content_hash": content_hash,
            "metadata": metadata,
            "confidence": confidence_for(metadata),
        },
        structured_text,
    )


def upsert_document(connection, document: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO semantic_documents(
          id, source_id, capture_id, title, path, url, source_type, content_hash, metadata_json, indexed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          source_id=excluded.source_id,
          capture_id=excluded.capture_id,
          title=excluded.title,
          path=excluded.path,
          url=excluded.url,
          source_type=excluded.source_type,
          content_hash=excluded.content_hash,
          metadata_json=excluded.metadata_json,
          indexed_at=excluded.indexed_at,
          status='active',
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            document["id"],
            document["source_id"],
            document["capture_id"],
            document["title"],
            document["path"],
            document["url"],
            document["source_type"],
            document["content_hash"],
            json.dumps(document["metadata"], sort_keys=True),
            utc_now(),
        ),
    )


def delete_document_chunks(connection, document_id: str) -> None:
    rows = connection.execute("SELECT id FROM semantic_chunks WHERE document_id = ?", (document_id,)).fetchall()
    for row in rows:
        connection.execute("DELETE FROM semantic_chunks_fts WHERE chunk_id = ?", (row["id"],))
    connection.execute("DELETE FROM semantic_chunks WHERE document_id = ?", (document_id,))


def unchanged_document_has_chunks(connection, document: dict[str, Any]) -> bool:
    row = connection.execute(
        """
        SELECT d.content_hash, COUNT(c.id) AS chunk_count
        FROM semantic_documents d
        LEFT JOIN semantic_chunks c ON c.document_id = d.id
        WHERE d.id = ?
        GROUP BY d.id
        """,
        (document["id"],),
    ).fetchone()
    return bool(row and row["content_hash"] == document["content_hash"] and row["chunk_count"] > 0)


def prune_stale_documents(connection, active_document_ids: set[str]) -> int:
    rows = connection.execute("SELECT id FROM semantic_documents").fetchall()
    stale_ids = [row["id"] for row in rows if row["id"] not in active_document_ids]
    for document_id in stale_ids:
        delete_document_chunks(connection, document_id)
        connection.execute("DELETE FROM semantic_documents WHERE id = ?", (document_id,))
    return len(stale_ids)


def insert_chunk(connection, document: dict[str, Any], chunk: dict[str, Any], chunk_index: int) -> None:
    text = chunk["text"]
    text_hash = sha256_text(text)
    graph_nodes = infer_graph_nodes(Path(document["path"]), document["title"], text)
    document_slug = slug(document["id"], max_len=72)
    document_hash = sha256_text(document["id"])[:10]
    chunk_id = f"chunk:{document_slug}:{document_hash}:{chunk_index:04d}:{text_hash[:12]}"
    metadata = {
        "path": document["path"],
        "url": document["url"],
        "content_hash": document["content_hash"],
        "chunking_strategy": chunk.get("chunking_strategy", "legacy"),
        "parent_context": chunk.get("parent_context", ""),
        "block_types": chunk.get("block_types", []),
        "boundary_rationale": chunk.get("boundary_rationale", []),
        "previous_context": chunk.get("previous_context", ""),
        "overlap_chars": chunk.get("overlap_chars", 0),
    }
    intake = document["metadata"].get("intake") if isinstance(document["metadata"].get("intake"), dict) else {}
    if intake:
        metadata["intake"] = {
            "media_type": intake.get("media_type", ""),
            "converter_name": intake.get("converter_name", ""),
            "parse_quality": intake.get("parse_quality", {}),
            "unit_counts": intake.get("unit_counts", {}),
            "warnings": intake.get("warnings", []),
        }
    connection.execute(
        """
        INSERT INTO semantic_chunks(
          id, document_id, source_id, capture_id, chunk_index, title, section, text,
          text_hash, token_estimate, source_type, confidence, graph_node_ids_json, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk_id,
            document["id"],
            document["source_id"],
            document["capture_id"],
            chunk_index,
            document["title"],
            chunk.get("section", ""),
            text,
            text_hash,
            estimate_tokens(text),
            document["source_type"],
            document["confidence"],
            json.dumps(graph_nodes, sort_keys=True),
            json.dumps(metadata, sort_keys=True),
        ),
    )
    connection.execute(
        "INSERT INTO semantic_chunks_fts(chunk_id, title, section, text) VALUES (?, ?, ?, ?)",
        (chunk_id, document["title"], chunk.get("section", ""), text),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--db", default=str(DEFAULT_VECTOR_DB))
    parser.add_argument("--file", action="append", help="Specific file to chunk. Can be repeated.")
    parser.add_argument("--include-skills", action="store_true", default=True)
    parser.add_argument("--no-skills", action="store_false", dest="include_skills")
    parser.add_argument("--include-runtimes", action="store_true", default=True)
    parser.add_argument("--no-runtimes", action="store_false", dest="include_runtimes")
    parser.add_argument("--target-chars", type=int, default=1800)
    parser.add_argument("--overlap-chars", type=int, default=250)
    parser.add_argument(
        "--chunk-strategy",
        choices=["auto", "legacy", "markdown", "code", "json", "plain"],
        default="auto",
        help="Chunking strategy. auto uses document structure; legacy preserves the original block chunker.",
    )
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--reset", action="store_true", help="Clear existing documents, chunks, and embeddings first.")
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Skip documents whose normalized content hash and existing chunks are unchanged.",
    )
    parser.add_argument(
        "--prune-stale",
        action="store_true",
        help="Delete indexed documents that are no longer present in the current discovered file set.",
    )
    args = parser.parse_args()

    root = Path(args.root)
    files = (
        [Path(value).expanduser() for value in args.file]
        if args.file
        else default_files(root, include_skills=args.include_skills, include_runtimes=args.include_runtimes)
    )
    if args.max_files:
        files = files[: args.max_files]

    with connect(Path(args.db)) as connection:
        ensure_schema(connection)
        if args.reset:
            connection.execute("DELETE FROM semantic_chunks_fts")
            connection.execute("DELETE FROM chunk_embeddings")
            connection.execute("DELETE FROM semantic_chunks")
            connection.execute("DELETE FROM semantic_documents")

        document_count = 0
        chunk_count = 0
        skipped = 0
        unchanged = 0
        pruned = 0
        seen_document_ids: set[str] = set()
        for path in files:
            if not path.exists() or not path.is_file():
                skipped += 1
                continue
            document, text = document_record(path, root)
            seen_document_ids.add(document["id"])
            if args.changed_only and not args.reset and unchanged_document_has_chunks(connection, document):
                unchanged += 1
                continue
            chunks = chunk_text(
                text,
                target_chars=args.target_chars,
                overlap_chars=args.overlap_chars,
                strategy=args.chunk_strategy,
                path=document["path"],
                source_type=document["source_type"],
                title=document["title"],
            )
            if not chunks:
                skipped += 1
                continue
            upsert_document(connection, document)
            delete_document_chunks(connection, document["id"])
            for idx, chunk in enumerate(chunks, 1):
                insert_chunk(connection, document, chunk, idx)
                chunk_count += 1
            document_count += 1

        if args.prune_stale and not args.file:
            pruned = prune_stale_documents(connection, seen_document_ids)

    print(f"Chunked documents: {document_count}")
    print(f"Chunks: {chunk_count}")
    print(f"Skipped: {skipped}")
    print(f"Unchanged: {unchanged}")
    print(f"Pruned: {pruned}")
    print(f"Vector DB: {Path(args.db)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
