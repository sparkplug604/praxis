#!/usr/bin/env python3
"""Create a Markdown analysis stub for a new Praxis source."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from praxis.paths import default_root, notes_dir


DEFAULT_NOTES = notes_dir(default_root())


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug or "source"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", help="Source title")
    parser.add_argument("--year", default="", help="Publication/document year")
    parser.add_argument("--url", default="", help="Source URL")
    parser.add_argument("--notes", default=str(DEFAULT_NOTES), help="Notes directory")
    args = parser.parse_args()

    notes = Path(args.notes)
    notes.mkdir(parents=True, exist_ok=True)
    path = notes / f"{args.year + '-' if args.year else ''}{slugify(args.title)}.md"

    if path.exists():
        print(f"Already exists: {path}")
        return 0

    path.write_text(
        f"""# {args.title}

- Year: {args.year or 'TBD'}
- URL: {args.url or 'TBD'}
- Source type: TBD
- Status: stub

## Core Idea

TBD

## Architecture Pattern

TBD

## Evidence

TBD

## Critical Notes

TBD

## Agent Implications

TBD

## Safety / Governance Implications

TBD

## Failure Modes

TBD

## Scores

- Agent relevance: TBD
- Engineering relevance: TBD
- Evidence strength: TBD
- Reproducibility: TBD
- Safety/governance relevance: TBD
"""
    )
    print(f"Created {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
