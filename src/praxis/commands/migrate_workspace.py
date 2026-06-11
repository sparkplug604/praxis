#!/usr/bin/env python3
"""Move legacy root-level Praxis runtime files into workspace/ safely."""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

from praxis.paths import default_root, ensure_workspace_dirs, legacy_runtime_paths, runtime_dir, workspace_root


RUNTIME_DIRS = [
    "db",
    "kg",
    "vectors",
    "research",
    "sources",
    "exports",
    "watchlists",
    "skills",
    "notes",
    "reach",
    "agency",
]

SOURCE_CONTROLLED_NAMES = {
    ".gitkeep",
    ".gitignore",
    ".env.example",
    "README.md",
    "schema.sql",
    "seed_graph.json",
    "seed_sources.json",
    "runtime_corpus.example.json",
    "agent_research.example.json",
}


@dataclass(frozen=True)
class MigrationItem:
    source: Path
    target: Path
    action: str
    reason: str


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def should_skip(path: Path) -> bool:
    return path.name in SOURCE_CONTROLLED_NAMES


def collect_items(root: Path) -> list[MigrationItem]:
    items: list[MigrationItem] = []
    workspace = workspace_root(root).resolve()
    for name in RUNTIME_DIRS:
        legacy = legacy_runtime_paths(root)[name]
        if not legacy.exists():
            continue
        target_base = runtime_dir(root, name)
        if target_base.resolve() == legacy.resolve():
            target_base = workspace / name
        for path in sorted(legacy.rglob("*")):
            if path.is_dir() or should_skip(path):
                continue
            target = target_base / path.relative_to(legacy)
            if target.exists():
                items.append(MigrationItem(path, target, "skip", "target already exists"))
            else:
                items.append(MigrationItem(path, target, "move", "legacy runtime file"))
    return items


def print_plan(root: Path, items: list[MigrationItem]) -> None:
    print("# Praxis workspace migration plan")
    print(f"workspace: {workspace_root(root)}")
    if not items:
        print("status: nothing-to-migrate")
        return
    for item in items:
        print(f"{item.action}: {rel(root, item.source)} -> {rel(root, item.target)} ({item.reason})")
    skips = sum(1 for item in items if item.action == "skip")
    moves = sum(1 for item in items if item.action == "move")
    print(f"summary: {moves} move(s), {skips} skip(s)")


def apply_items(items: list[MigrationItem]) -> int:
    moved = 0
    skipped = 0
    for item in items:
        if item.action != "move":
            skipped += 1
            continue
        item.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(item.source), str(item.target))
        moved += 1
    print(f"applied: {moved} move(s), {skipped} skip(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(default_root()), help="Praxis checkout root.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="Show planned moves without writing. This is the default.")
    mode.add_argument("--apply", action="store_true", help="Move legacy runtime files into workspace/. Never overwrites.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    items = collect_items(root)
    print_plan(root, items)
    if not args.apply:
        return 0
    ensure_workspace_dirs(root)
    return apply_items(items)


if __name__ == "__main__":
    raise SystemExit(main())
