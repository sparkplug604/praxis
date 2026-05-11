#!/usr/bin/env python3
"""Add a durable, non-secret note to the Praxis memory corpus."""

from __future__ import annotations

import argparse
from pathlib import Path

from vector_common import DEFAULT_ROOT, slug, utc_now


def render_note(title: str, body: str, tags: str, source: str, status: str) -> str:
    created_at = utc_now()
    tag_line = ", ".join(part.strip() for part in tags.split(",") if part.strip())
    lines = [
        f"# {title}",
        "",
        f"- created_at: {created_at}",
        f"- status: {status}",
        f"- tags: {tag_line}",
    ]
    if source:
        lines.append(f"- source: {source}")
    lines.extend(
        [
            "",
            "## Note",
            "",
            body.strip(),
            "",
            "## Retrieval Guidance",
            "",
            "Use this note when the same decision, failure mode, or design pattern reappears in future agent work.",
            "",
        ]
    )
    return "\n".join(lines)


def unique_path(notes_dir: Path, base_slug: str) -> Path:
    candidate = notes_dir / f"{base_slug}.md"
    if not candidate.exists():
        return candidate
    for index in range(2, 1000):
        candidate = notes_dir / f"{base_slug}-{index}.md"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find a unique note path for {base_slug}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", help="Short retrieval-friendly note title.")
    parser.add_argument("--body", required=True, help="Reusable lesson or memory to store.")
    parser.add_argument("--tags", default="", help="Comma-separated tags.")
    parser.add_argument("--source", default="", help="Optional source path, URL, or context label.")
    parser.add_argument("--status", default="reviewed", choices=["draft", "reviewed"])
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    args = parser.parse_args()

    if any(marker in args.body.lower() for marker in ["sk-", "api key", "password=", "secret="]):
        raise SystemExit("Refusing to store likely secret material in memory.")

    root = Path(args.root)
    notes_dir = root / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    path = unique_path(notes_dir, f"memory-{slug(args.title)}")
    path.write_text(render_note(args.title, args.body, args.tags, args.source, args.status), encoding="utf-8")

    print(f"Wrote memory note: {path}")
    print("Next indexing steps:")
    print(f"  python3 {root / 'scripts' / 'chunk_sources.py'} --changed-only")
    print(f"  python3 {root / 'scripts' / 'index_vectors.py'} --provider local-hash")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
