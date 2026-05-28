from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
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


def conflict_from(output: str, conflict_type: str) -> str:
    match = re.search(rf"(conflict:{re.escape(conflict_type)}:[^\s]+)", output)
    if not match:
        raise AssertionError(f"No {conflict_type} conflict found in output:\n{output}")
    return match.group(1)


class ReleaseHardeningTests(unittest.TestCase):
    def test_ingest_initializes_missing_skill_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            source = write_source(root)

            ingest = run_praxis(root, "ingest", str(source), "--source-type", "docs", "--risk-level", "low")

            self.assertIn("Ingested Semantic Contract Test Source", ingest.stdout)
            self.assertIn("change_set_id:", ingest.stdout)

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

    def test_duplicate_content_conflict_can_be_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            source = write_source(root)

            run_praxis(root, "ingest", str(source), "--source-id", "src:duplicate-a", "--title", "Duplicate A", "--source-type", "docs", "--risk-level", "low")
            second = run_praxis(root, "ingest", str(source), "--source-id", "src:duplicate-b", "--title", "Duplicate B", "--source-type", "docs", "--risk-level", "low")
            self.assertIn("conflict_warnings:", second.stdout)

            listed = run_praxis(root, "conflicts", "list", "--type", "duplicate_content")
            conflict_id = conflict_from(listed.stdout, "duplicate_content")
            shown = run_praxis(root, "conflicts", "show", conflict_id)
            self.assertIn("Duplicate captured content hash", shown.stdout)

            run_praxis(root, "chunk", "--reset", "--no-runtimes", "--no-skills")
            run_praxis(root, "embed", "--provider", "local-hash")
            search = run_praxis(root, "search", "semantic contract", "--limit", "2", "--explain")
            self.assertIn("conflict_warnings:", search.stdout)

            refused_export = run_praxis(root, "export-graph", "--fail-on-open-conflicts", check=False)
            self.assertEqual(2, refused_export.returncode, refused_export.stdout)
            self.assertIn("Refusing export", refused_export.stdout)

            resolved = run_praxis(root, "conflicts", "resolve", conflict_id, "--resolution", "keep_both_with_scope", "--notes", "test")
            self.assertIn("status: resolved", resolved.stdout)
            open_list = run_praxis(root, "conflicts", "list", "--type", "duplicate_content")
            self.assertIn("No conflicts found.", open_list.stdout)

    def test_claim_contradiction_is_logged(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            init_root(root)
            first = root / "research" / "proposals" / "use-sqlite.json"
            second = root / "research" / "proposals" / "avoid-sqlite.json"
            first.write_text(
                json.dumps(
                    {
                        "id": "proposal:use-sqlite",
                        "title": "Use SQLite",
                        "risk_level": "low",
                        "summary": "Positive claim.",
                        "nodes": [
                            {
                                "id": "claim:use-sqlite",
                                "type": "claim",
                                "name": "Use SQLite",
                                "summary": "Use SQLite for local memory.",
                                "confidence": "medium",
                                "status": "provisional",
                            }
                        ],
                        "edges": [],
                        "evidence": [],
                    }
                ),
                encoding="utf-8",
            )
            second.write_text(
                json.dumps(
                    {
                        "id": "proposal:avoid-sqlite",
                        "title": "Avoid SQLite",
                        "risk_level": "low",
                        "summary": "Negative claim.",
                        "nodes": [
                            {
                                "id": "claim:avoid-sqlite",
                                "type": "claim",
                                "name": "Avoid SQLite",
                                "summary": "Avoid SQLite for local memory.",
                                "confidence": "medium",
                                "status": "provisional",
                            }
                        ],
                        "edges": [],
                        "evidence": [],
                    }
                ),
                encoding="utf-8",
            )

            run_praxis(root, "apply", str(first))
            applied = run_praxis(root, "apply", str(second))
            self.assertIn("Conflict warnings:", applied.stdout)
            listed = run_praxis(root, "conflicts", "list", "--type", "contradiction")
            self.assertIn("Possible contradiction", listed.stdout)

    def test_duplicate_entity_merge_and_split_are_reversible(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            first = root / "notes" / "jack.md"
            second = root / "notes" / "dr-jack.md"
            first.write_text("# Jack Abbott\n\nJack Abbott is an example entity for dedupe testing.\n", encoding="utf-8")
            second.write_text("# Dr. Jack Abbott\n\nDr. Jack Abbott is the same example entity for dedupe testing.\n", encoding="utf-8")

            run_praxis(root, "ingest", str(first), "--source-type", "docs", "--risk-level", "low")
            run_praxis(root, "ingest", str(second), "--source-type", "docs", "--risk-level", "low")

            listed = run_praxis(root, "dedupe", "list")
            conflict_id = conflict_from(listed.stdout, "duplicate_entity")
            merged = run_praxis(root, "dedupe", "merge", conflict_id, "--canonical", "external:jack-abbott")
            merge_change_set = change_set_from(merged.stdout)

            with sqlite3.connect(root / "kg" / "skill_graph.sqlite") as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute("SELECT status FROM nodes WHERE id = 'external:dr-jack-abbott'").fetchone()
                self.assertEqual("merged", row["status"])

            split = run_praxis(root, "dedupe", "split", merge_change_set)
            self.assertIn("Reverted dedupe merge", split.stdout)
            self.assertIn("Reopened dedupe conflicts: 1", split.stdout)
            with sqlite3.connect(root / "kg" / "skill_graph.sqlite") as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute("SELECT status FROM nodes WHERE id = 'external:dr-jack-abbott'").fetchone()
                self.assertEqual("provisional", row["status"])


if __name__ == "__main__":
    unittest.main()
