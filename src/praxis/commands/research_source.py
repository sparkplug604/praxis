#!/usr/bin/env python3
"""Capture one live/local source into the SkillGraph research store."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse

from research_common import (
    DEFAULT_ROOT,
    connect,
    credibility_score,
    infer_source_type,
    read_source_extraction,
    register_capture,
    register_source,
    sha256_text,
    slug,
    summarize_text,
    title_from_source,
    utc_now,
    write_json,
)
from conflict_ledger import scan_source_dedupe
from init_skill_graph import ensure_skill_graph_initialized
from praxis.paths import kg_dir, research_dir


def capture_source(
    *,
    root: Path,
    source: str,
    title: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    freshness_window_days: int = 30,
    notes: str = "",
) -> dict:
    db_path = kg_dir(root) / "skill_graph.sqlite"
    captures_root = research_dir(root) / "captures"

    extraction = read_source_extraction(source)
    text, metadata = extraction.to_legacy()
    if not text.strip():
        warnings = ", ".join(extraction.warnings or metadata.get("intake_warnings", []))
        raise RuntimeError(f"No searchable text extracted from {source}. {warnings}".strip())
    content_hash = sha256_text(text)
    resolved_source_type = source_type or infer_source_type(source, text)
    resolved_title = title or title_from_source(source, text)
    resolved_source_id = source_id or f"src:{slug(resolved_title or source)}"
    capture_id = f"cap:{slug(resolved_source_id)}:{content_hash[:12]}"
    credibility = credibility_score(resolved_source_type, metadata)

    source_dir = captures_root / slug(resolved_source_id)
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / f"{slug(capture_id)}.raw.txt"
    summary_path = source_dir / f"{slug(capture_id)}.summary.md"
    metadata_path = source_dir / f"{slug(capture_id)}.metadata.json"
    artifact_path = source_dir / f"{slug(capture_id)}.artifact{artifact_suffix(source)}"

    raw_path.write_text(text, encoding="utf-8")
    if extraction.artifact_bytes:
        artifact_path.write_bytes(extraction.artifact_bytes)
    summary = summarize_text(text)
    summary_path.write_text(
        "\n".join(
            [
                f"# {resolved_title}",
                "",
                f"- source: {source}",
                f"- source_id: `{resolved_source_id}`",
                f"- capture_id: `{capture_id}`",
                f"- captured_at: {utc_now()}",
                f"- source_type: {resolved_source_type}",
                f"- content_hash: `{content_hash}`",
                "",
                "## Extractive Summary",
                "",
                summary,
                "",
            ]
        ),
        encoding="utf-8",
    )
    metadata_record = {
        "source": source,
        "source_id": resolved_source_id,
        "capture_id": capture_id,
        "title": resolved_title,
        "source_type": resolved_source_type,
        "content_hash": content_hash,
        "credibility_score": credibility,
        "freshness_window_days": freshness_window_days,
        "raw_path": str(raw_path),
        "summary_path": str(summary_path),
        "artifact_path": str(artifact_path) if extraction.artifact_bytes else "",
        "metadata": metadata,
        "intake": extraction.to_metadata(),
    }
    write_json(metadata_path, metadata_record)

    ensure_skill_graph_initialized(root, quiet=True)
    with connect(db_path) as connection:
        register_source(
            connection,
            source_id=resolved_source_id,
            url=source if source.startswith(("http://", "https://")) else "",
            title=resolved_title,
            source_type=resolved_source_type,
            canonical_ref=source,
            freshness_window_days=freshness_window_days,
            credibility=credibility,
            notes=notes,
            metadata=metadata,
        )
        register_capture(
            connection,
            capture_id=capture_id,
            source_id=resolved_source_id,
            content_hash=content_hash,
            raw_path=str(raw_path),
            summary_path=str(summary_path),
            metadata={
                "metadata_path": str(metadata_path),
                "artifact_path": str(artifact_path) if extraction.artifact_bytes else "",
                "intake": extraction.to_metadata(),
                **metadata,
            },
        )
        conflict_ids = scan_source_dedupe(connection, source_id=resolved_source_id, capture_id=capture_id)

    return {
        **metadata_record,
        "raw_path": raw_path,
        "summary_path": summary_path,
        "metadata_path": metadata_path,
        "conflict_ids": conflict_ids,
    }


def artifact_suffix(source: str) -> str:
    candidate = urlparse(source).path if source.startswith(("http://", "https://")) else source
    suffix = Path(candidate).suffix.lower()
    if 1 < len(suffix) <= 12 and all(char.isalnum() or char == "." for char in suffix):
        return suffix
    return ".bin"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="URL, local file, or local directory to capture")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--title", help="Override source title")
    parser.add_argument("--source-type", help="Override source type")
    parser.add_argument("--source-id", help="Override source id")
    parser.add_argument("--freshness-window-days", type=int, default=30)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    root = Path(args.root)
    capture = capture_source(
        root=root,
        source=args.source,
        title=args.title,
        source_type=args.source_type,
        source_id=args.source_id,
        freshness_window_days=args.freshness_window_days,
        notes=args.notes,
    )
    print(f"Captured {capture['title']}")
    print(f"source_id: {capture['source_id']}")
    print(f"capture_id: {capture['capture_id']}")
    print(f"raw: {capture['raw_path']}")
    print(f"summary: {capture['summary_path']}")
    if capture.get("conflict_ids"):
        print("conflict_warnings:")
        for conflict_id in capture["conflict_ids"]:
            print(f"- {conflict_id}")
    print()
    print("Next:")
    print(f"  python3.12 \"{root / 'scripts' / 'propose_graph_update.py'}\" {capture['capture_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
