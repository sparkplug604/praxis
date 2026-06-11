"""Path helpers for a local Praxis checkout and workspace."""

from __future__ import annotations

import os
from pathlib import Path


WORKSPACE_DIRNAME = "workspace"
BOOTSTRAP_DIRNAME = "bootstrap"


def package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_root() -> Path:
    """Return the active Praxis root.

    `PRAXIS_ROOT` lets packaged installs operate on a separate workspace while
    local checkouts default to the repository root.
    """

    configured = os.environ.get("PRAXIS_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    root = package_root()
    if (root / "scripts").exists():
        return root

    cwd = Path.cwd().resolve()
    if (cwd / "scripts").exists():
        return cwd

    return root


def scripts_dir(root: Path | None = None) -> Path:
    return (root or default_root()) / "scripts"


def commands_dir() -> Path:
    return Path(__file__).resolve().parent / "commands"


def coerce_root(root: Path | str | None = None) -> Path:
    return Path(root or default_root()).expanduser().resolve()


def workspace_root(root: Path | str | None = None) -> Path:
    configured = os.environ.get("PRAXIS_WORKSPACE")
    if configured:
        return Path(configured).expanduser().resolve()
    return coerce_root(root) / WORKSPACE_DIRNAME


def bootstrap_root(root: Path | str | None = None) -> Path:
    base = coerce_root(root)
    candidate = base / BOOTSTRAP_DIRNAME
    return candidate if candidate.exists() else base


def bootstrap_path(root: Path | str | None, *parts: str) -> Path:
    return bootstrap_root(root).joinpath(*parts)


def workspace_path(root: Path | str | None, *parts: str) -> Path:
    return workspace_root(root).joinpath(*parts)


def runtime_dir(root: Path | str | None, name: str) -> Path:
    """Return a generated-data directory with one-release legacy fallback.

    New workspaces live under ``workspace/<name>``. If an older checkout has a
    root-level runtime directory and no migrated workspace directory, keep using
    the legacy directory so existing installs do not break immediately.
    """

    base = coerce_root(root)
    modern = workspace_root(base) / name
    legacy = base / name
    if modern.exists() or not legacy.exists():
        return modern
    return legacy


def db_dir(root: Path | str | None = None) -> Path:
    return runtime_dir(root, "db")


def kg_dir(root: Path | str | None = None) -> Path:
    return runtime_dir(root, "kg")


def vectors_dir(root: Path | str | None = None) -> Path:
    return runtime_dir(root, "vectors")


def research_dir(root: Path | str | None = None) -> Path:
    return runtime_dir(root, "research")


def sources_dir(root: Path | str | None = None) -> Path:
    return runtime_dir(root, "sources")


def exports_dir(root: Path | str | None = None) -> Path:
    return runtime_dir(root, "exports")


def watchlists_dir(root: Path | str | None = None) -> Path:
    return runtime_dir(root, "watchlists")


def skills_dir(root: Path | str | None = None) -> Path:
    return runtime_dir(root, "skills")


def notes_dir(root: Path | str | None = None) -> Path:
    return runtime_dir(root, "notes")


def reach_dir(root: Path | str | None = None) -> Path:
    return runtime_dir(root, "reach")


def agency_dir(root: Path | str | None = None) -> Path:
    return runtime_dir(root, "agency")


def ensure_workspace_dirs(root: Path | str | None = None) -> list[Path]:
    workspace = workspace_root(root)
    paths = [
        workspace / "db",
        workspace / "kg",
        workspace / "vectors",
        workspace / "research" / "captures",
        workspace / "research" / "proposals",
        workspace / "research" / "applied",
        workspace / "research" / "rejected",
        workspace / "research" / "inbox",
        workspace / "research" / "demo_sources",
        workspace / "sources",
        workspace / "exports",
        workspace / "watchlists",
        workspace / "skills",
        workspace / "notes",
        workspace / "reach",
        workspace / "agency" / "clients",
        workspace / "agency" / "lifecycle",
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    return paths


def legacy_runtime_paths(root: Path | str | None = None) -> dict[str, Path]:
    base = coerce_root(root)
    return {
        "db": base / "db",
        "kg": base / "kg",
        "vectors": base / "vectors",
        "research": base / "research",
        "sources": base / "sources",
        "exports": base / "exports",
        "watchlists": base / "watchlists",
        "skills": base / "skills",
        "notes": base / "notes",
        "reach": base / "reach",
        "agency": base / "agency",
    }


def active_runtime_paths(root: Path | str | None = None) -> dict[str, Path]:
    return {name: runtime_dir(root, name) for name in legacy_runtime_paths(root)}
