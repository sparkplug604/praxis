#!/usr/bin/env python3
"""Run lightweight retrieval checks against the semantic index."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from vector_common import DEFAULT_ROOT


DEFAULT_EVALS = [
    {
        "query": "Praxis knowledge to skill framework",
        "expect": ["Praxis", "knowledge", "skill"],
    },
    {
        "query": "provisional graph update audit rollback",
        "expect": ["provisional", "graph", "rollback"],
    },
    {
        "query": "hybrid retrieval semantic keyword graph",
        "expect": ["hybrid", "retrieval", "graph"],
    },
    {
        "query": "agent skill package progressive disclosure",
        "expect": ["skill", "progressive", "disclosure"],
    },
    {
        "query": "unsupported memory write mitigation",
        "expect": ["unsupported", "memory", "evidence"],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--text-chars", type=int, default=1600)
    args = parser.parse_args()

    root = Path(args.root)
    script = root / "scripts" / "hybrid_search.py"
    passed = 0

    for idx, case in enumerate(DEFAULT_EVALS, 1):
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                case["query"],
                "--limit",
                str(args.limit),
                "--show-text",
                "--text-chars",
                str(args.text_chars),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        output = result.stdout + result.stderr
        missing = [term for term in case["expect"] if term.lower() not in output.lower()]
        ok = result.returncode == 0 and not missing
        passed += 1 if ok else 0
        print(f"{idx}. {'PASS' if ok else 'FAIL'}: {case['query']}")
        if missing:
            print(f"   missing: {', '.join(missing)}")
        if result.returncode != 0:
            print(f"   returncode: {result.returncode}")

    print()
    print(f"Passed: {passed}/{len(DEFAULT_EVALS)}")
    return 0 if passed == len(DEFAULT_EVALS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
