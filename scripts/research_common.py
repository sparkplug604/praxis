"""Compatibility re-export for packaged Praxis research helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from praxis.commands.research_common import *  # noqa: F401,F403
