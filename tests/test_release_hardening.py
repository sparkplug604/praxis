from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def copy_fixture(source: str, root: Path) -> None:
    src = REPO / source
    dst = root / source
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def make_root(tempdir: str) -> Path:
    root = Path(tempdir)
    for path in [
        "db",
        "kg",
        "research/captures",
        "research/proposals",
        "research/applied",
        "research/rejected",
        "research/inbox",
        "sources",
        "vectors",
        "watchlists",
        "exports",
        "notes",
    ]:
        (root / path).mkdir(parents=True, exist_ok=True)
    for fixture in [
        "db/schema.sql",
        "kg/schema.sql",
        "kg/seed_graph.json",
        "sources/seed_sources.json",
    ]:
        copy_fixture(fixture, root)
    return root


def run_praxis(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO / "src")
    env["PYTHONPYCACHEPREFIX"] = str(root / ".pycache")
    result = subprocess.run(
        [sys.executable, "-m", "praxis", "--root", str(root), *args],
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(f"praxis {' '.join(args)} failed with {result.returncode}\n{result.stdout}")
    return result


def init_root(root: Path) -> None:
    run_praxis(root, "init-db")
    run_praxis(root, "init-graph")


def write_source(root: Path) -> Path:
    source = root / "notes" / "semantic-contracts.md"
    source.write_text(
        "\n".join(
            [
                "# Semantic Contract Test Source",
                "",
                "Agents should use a task semantic contract before parallel work starts.",
                "The contract records assumptions, acceptance criteria, dependencies, and intended outputs.",
                "The runtime should support reasoning branch merge, context distillation, and divergence detection.",
                "Rollback and audit logs keep provisional graph updates reversible.",
            ]
        ),
        encoding="utf-8",
    )
    return source


def change_set_from(output: str) -> str:
    match = re.search(r"change_set_id:\s*(chg:[^\s]+)", output)
    if not match:
        raise AssertionError(f"No change_set_id found in output:\n{output}")
    return match.group(1)


class ReleaseHardeningTests(unittest.TestCase):
    def test_ingest_promote_deprecate_and_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            init_root(root)
            source = write_source(root)

            ingest = run_praxis(root, "ingest", str(source), "--source-type", "docs", "--risk-level", "low")
            change_set = change_set_from(ingest.stdout)

            provisional = run_praxis(root, "graph", "search", "Semantic Contract Test Source")
            self.assertIn("status: provisional", provisional.stdout)

            promoted = run_praxis(root, "promote", change_set)
            self.assertIn("Objects changed:", promoted.stdout)
            active = run_praxis(root, "graph", "search", "Semantic Contract Test Source")
            self.assertIn("status: active", active.stdout)

            deprecated = run_praxis(root, "deprecate", change_set)
            self.assertIn("Objects changed:", deprecated.stdout)
            hidden = run_praxis(root, "graph", "search", "Semantic Contract Test Source")
            self.assertIn("No matching nodes.", hidden.stdout)

            inactive = run_praxis(root, "graph", "--include-inactive", "search", "Semantic Contract Test Source")
            self.assertIn("status: deprecated", inactive.stdout)

    def test_rollback_refuses_after_later_change_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            init_root(root)
            source = write_source(root)

            ingest = run_praxis(root, "ingest", str(source), "--source-type", "docs", "--risk-level", "low")
            change_set = change_set_from(ingest.stdout)
            run_praxis(root, "promote", change_set)

            refused = run_praxis(root, "rollback", change_set, check=False)
            self.assertEqual(2, refused.returncode, refused.stdout)
            self.assertIn("Refusing rollback", refused.stdout)
            self.assertIn("Use --force", refused.stdout)

            forced = run_praxis(root, "rollback", change_set, "--force")
            self.assertIn("Rolled back change set", forced.stdout)
            hidden = run_praxis(root, "graph", "search", "Semantic Contract Test Source")
            self.assertIn("No matching nodes.", hidden.stdout)

    def test_search_explain_prints_score_and_source_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            init_root(root)
            source = write_source(root)

            run_praxis(root, "ingest", str(source), "--source-type", "docs", "--risk-level", "low")
            run_praxis(root, "chunk", "--reset", "--no-runtimes", "--no-skills")
            run_praxis(root, "embed", "--provider", "local-hash")

            result = run_praxis(root, "search", "task semantic contract", "--limit", "3", "--explain")
            self.assertIn("explain:", result.stdout)
            self.assertIn("source_id:", result.stdout)
            self.assertIn("graph_hints_used:", result.stdout)


if __name__ == "__main__":
    unittest.main()
