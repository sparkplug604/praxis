#!/usr/bin/env python3
"""Compatibility wrapper for Praxis agency commands."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from praxis.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["agency", *sys.argv[1:]]))
