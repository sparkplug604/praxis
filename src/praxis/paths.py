"""Path helpers for a local Praxis checkout."""

from __future__ import annotations

import os
from pathlib import Path


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
