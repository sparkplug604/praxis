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
    src = REPO / "bootstrap" / source
    dst = root / "bootstrap" / source
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def make_root(tempdir: str) -> Path:
    root = Path(tempdir)
    for path in [
        "bootstrap/db",
        "bootstrap/kg",
        "bootstrap/sources",
        "workspace/db",
        "workspace/kg",
        "workspace/vectors",
        "workspace/notes",
        "workspace/research/captures",
        "workspace/research/proposals",
        "workspace/research/applied",
        "workspace/research/rejected",
        "workspace/sources",
        "workspace/watchlists",
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


def seed_account(root: Path) -> None:
    db_path = root / "workspace" / "kg" / "skill_graph.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO nodes(id, type, name, summary, confidence, status, source_ref)
            VALUES ('account:acme', 'account', 'Acme Corp', 'A fixture account for entity-aware retrieval.', 'high', 'active', 'hubspot')
            ON CONFLICT(id) DO UPDATE SET name=excluded.name
            """
        )
        connection.execute("INSERT OR IGNORE INTO aliases(node_id, alias) VALUES ('account:acme', 'Acme')")
        connection.execute("INSERT OR IGNORE INTO aliases(node_id, alias) VALUES ('account:acme', 'ACME Corp')")


def write_note(root: Path) -> Path:
    path = root / "workspace" / "notes" / "acme-pipeline.md"
    path.write_text(
        "\n".join(
            [
                "# Acme Pipeline Note",
                "",
                "Acme Corp has a growing pipeline this quarter.",
                "The ACME Corp expansion campaign is tied to enterprise opportunities.",
            ]
        ),
        encoding="utf-8",
    )
    return path


def annotation_id_from(output: str) -> str:
    match = re.search(r"(ann:[a-f0-9]+)", output)
    if not match:
        raise AssertionError(f"No annotation id found:\n{output}")
    return match.group(1)


class EntityAwareRetrievalTests(unittest.TestCase):
    def test_entities_extract_resolve_explain_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            run_praxis(root, "init-db")
            run_praxis(root, "init-graph")
            seed_account(root)
            note = write_note(root)
            run_praxis(root, "chunk", "--file", str(note), "--reset", "--no-runtimes", "--no-skills")
            run_praxis(root, "entities", "init")

            extracted = run_praxis(root, "entities", "extract", "--changed-only")
            self.assertIn("mentions_written:", extracted.stdout)

            resolved = run_praxis(root, "entities", "resolve")
            self.assertIn("accepted:", resolved.stdout)
            self.assertNotIn("accepted: 0", resolved.stdout)

            mentions = run_praxis(root, "entities", "mentions", "--status", "accepted")
            self.assertIn("account:acme", mentions.stdout)
            annotation_id = annotation_id_from(mentions.stdout)

            explained = run_praxis(root, "entities", "explain", "Acme")
            self.assertIn("node_id: account:acme", explained.stdout)
            self.assertIn("resolved_mentions:", explained.stdout)

            entity_search = run_praxis(root, "entities", "search", "Acme pipeline", "--show-text")
            self.assertIn("account:acme", entity_search.stdout)
            self.assertIn("Acme Corp has a growing pipeline", entity_search.stdout)

            hybrid = run_praxis(root, "search", "Acme pipeline", "--entity-aware", "--explain")
            self.assertIn("entity_links:", hybrid.stdout)
            self.assertIn("account:acme", hybrid.stdout)

            shown = run_praxis(root, "entities", "annotation", annotation_id)
            payload = json.loads(shown.stdout)
            self.assertEqual("accepted", payload["status"])
            self.assertIn("account:acme", payload["resolved_entity_ids"])

    def test_governance_can_evaluate_entity_annotation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            run_praxis(root, "init-db")
            run_praxis(root, "init-graph")
            seed_account(root)
            note = write_note(root)
            run_praxis(root, "chunk", "--file", str(note), "--reset", "--no-runtimes", "--no-skills")
            run_praxis(root, "entities", "extract")
            run_praxis(root, "entities", "resolve")
            mentions = run_praxis(root, "entities", "mentions", "--status", "accepted")
            annotation_id = annotation_id_from(mentions.stdout)

            run_praxis(root, "authority", "init")
            run_praxis(root, "authority", "compile")
            run_praxis(root, "governance", "init")
            evaluated = run_praxis(
                root,
                "governance",
                "evaluate",
                "--claim-type",
                "entity_identity",
                "--source",
                "entity_annotation",
                "--evidence",
                annotation_id,
            )
            self.assertIn("evidence_kind: evidence_annotation", evaluated.stdout)
            self.assertIn("entity_resolution_status: accepted", evaluated.stdout)
            self.assertIn("resolved_entity_ids: account:acme", evaluated.stdout)
            self.assertNotIn("evidence_exists: false", evaluated.stdout)

    def test_ambiguous_entity_resolution_requires_review(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            run_praxis(root, "init-db")
            run_praxis(root, "init-graph")
            db_path = root / "workspace" / "kg" / "skill_graph.sqlite"
            with sqlite3.connect(db_path) as connection:
                for node_id, name in [("account:acme-one", "Acme Corp"), ("account:acme-two", "Acme Corporation")]:
                    connection.execute(
                        "INSERT INTO nodes(id, type, name, summary, confidence, status) VALUES (?, 'account', ?, 'Ambiguous account.', 'medium', 'active')",
                        (node_id, name),
                    )
                    connection.execute("INSERT OR IGNORE INTO aliases(node_id, alias) VALUES (?, 'Acme')", (node_id,))
            note = write_note(root)
            run_praxis(root, "chunk", "--file", str(note), "--reset", "--no-runtimes", "--no-skills")
            run_praxis(root, "entities", "extract")
            resolved = run_praxis(root, "entities", "resolve")
            self.assertIn("needs_review:", resolved.stdout)
            self.assertNotIn("needs_review: 0", resolved.stdout)
            mentions = run_praxis(root, "entities", "mentions", "--status", "needs_review")
            self.assertIn("resolution_status: needs_review", mentions.stdout)


if __name__ == "__main__":
    unittest.main()
