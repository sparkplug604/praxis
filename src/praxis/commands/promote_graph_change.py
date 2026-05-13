#!/usr/bin/env python3
"""Promote provisional objects from an audited SkillGraph change set."""

from __future__ import annotations

import sys

from change_graph_status import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], command="promote"))
