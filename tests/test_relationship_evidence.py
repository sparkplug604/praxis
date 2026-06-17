from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from praxis.commands.vector_common import ensure_schema, sha256_text
from praxis.relationship_evidence.extraction import RuleRelationExtractor, extract_claims_from_text, extract_relation_candidates
from praxis.relationship_evidence.ontology import load_default_ontology
from praxis.relationship_evidence.patterns import DEFAULT_RELATION_PATTERN_SPECS, compile_relation_patterns
from praxis.relationship_evidence.promotion import promote_relation_candidates
from praxis.relationship_evidence.query import compare_entity_relationships, find_relationships
from praxis.relationship_evidence.service import RelationshipEvidenceService
from praxis.relationship_evidence.storage import connect_relationship_evidence_db


REPO = Path(__file__).resolve().parents[1]


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


def seed_chunk(vector_db: Path, text: str, *, chunk_id: str = "chunk:1") -> None:
    with connect_relationship_evidence_db(vector_db) as connection:
        ensure_schema(connection)
        connection.execute(
            """
            INSERT INTO semantic_documents(id, title, path, content_hash)
            VALUES ('doc:1', 'Relationship fixture', '/tmp/fixture.md', ?)
            ON CONFLICT(id) DO UPDATE SET content_hash=excluded.content_hash
            """,
            (sha256_text(text),),
        )
        connection.execute(
            """
            INSERT INTO semantic_chunks(
              id, document_id, chunk_index, title, section, text, text_hash, token_estimate
            )
            VALUES (?, 'doc:1', 0, 'Relationship fixture', '', ?, ?, 50)
            ON CONFLICT(document_id, chunk_index) DO UPDATE SET
              text=excluded.text,
              text_hash=excluded.text_hash
            """,
            (chunk_id, text, sha256_text(text)),
        )


class RelationshipEvidenceTests(unittest.TestCase):
    def test_default_relation_pattern_specs_compile(self) -> None:
        compiled = compile_relation_patterns(DEFAULT_RELATION_PATTERN_SPECS)
        self.assertEqual(len(DEFAULT_RELATION_PATTERN_SPECS), len(compiled))
        predicates = {item.spec.predicate for item in compiled}
        self.assertIn("acquired", predicates)
        self.assertIn("led_by", predicates)

    def test_rule_relation_extractor_matches_compatibility_wrapper(self) -> None:
        text = "Acme Corp acquired Northstar Analytics. Acme Corp is led by Jamie Lee."
        ontology = load_default_ontology()
        direct = RuleRelationExtractor(ontology=ontology).extract_claims(text, chunk_id="chunk:1")
        wrapped = extract_claims_from_text(text, chunk_id="chunk:1", ontology=ontology)
        self.assertEqual([claim.predicate for claim in wrapped], [claim.predicate for claim in direct])
        self.assertEqual([claim.object_value for claim in wrapped], [claim.object_value for claim in direct])

    def test_extract_promote_and_query_relationship_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            vector_db = Path(tempdir) / "semantic_index.sqlite"
            seed_chunk(vector_db, "Acme Corp acquired Northstar Analytics. Acme Corp is led by Jamie Lee.")

            extracted = extract_relation_candidates(vector_db=vector_db)
            self.assertEqual(1, extracted.chunks_scanned)
            self.assertEqual(2, extracted.candidates_written)

            promoted = promote_relation_candidates(vector_db=vector_db)
            self.assertEqual(2, promoted.accepted)
            self.assertEqual(0, promoted.needs_review)

            acquired = find_relationships(vector_db=vector_db, subject="Acme", predicate="acquired")
            self.assertEqual(1, len(acquired))
            self.assertEqual("Northstar Analytics", acquired[0]["object_value"])
            self.assertEqual("relation_claim", acquired[0]["evidence"]["annotation_type"])

            led_by = find_relationships(vector_db=vector_db, subject="Acme", predicate="led_by")
            self.assertEqual("Jamie Lee", led_by[0]["object_value"])

    def test_relationship_evidence_service_runs_full_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            vector_db = Path(tempdir) / "semantic_index.sqlite"
            seed_chunk(vector_db, "Acme Corp acquired Northstar Analytics.")
            service = RelationshipEvidenceService(vector_db=vector_db)

            extracted = service.extract_relations()
            promoted = service.promote_candidates()
            relationships = service.find_relationships(subject="Acme", predicate="acquired")

            self.assertEqual(1, extracted.candidates_written)
            self.assertEqual(1, promoted.accepted)
            self.assertEqual("Northstar Analytics", relationships[0]["object_value"])

    def test_compare_entities_reports_shared_relationship_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            vector_db = Path(tempdir) / "semantic_index.sqlite"
            seed_chunk(
                vector_db,
                "Acme Corp acquired Northstar Analytics. Beta Corp acquired Northstar Analytics.",
            )
            extract_relation_candidates(vector_db=vector_db)
            promote_relation_candidates(vector_db=vector_db)

            compared = compare_entity_relationships(vector_db=vector_db, left="Acme Corp", right="Beta Corp")
            self.assertEqual(1, len(compared["shared_relationships"]))
            self.assertEqual("acquired", compared["shared_relationships"][0]["predicate"])
            self.assertEqual("Northstar Analytics", compared["shared_relationships"][0]["object_value"])

    def test_one_to_one_cardinality_conflicts_are_routed_to_review(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            vector_db = Path(tempdir) / "semantic_index.sqlite"
            seed_chunk(vector_db, "Acme Corp is led by Jamie Lee. Acme Corp is led by Priya Shah.")
            extract_relation_candidates(vector_db=vector_db)

            promoted = promote_relation_candidates(vector_db=vector_db)
            self.assertEqual(1, promoted.accepted)
            self.assertEqual(1, promoted.needs_review)

            with sqlite3.connect(vector_db) as connection:
                reason = connection.execute("SELECT reason FROM relationship_evidence_review_items").fetchone()[0]
            self.assertEqual("cardinality_conflict", reason)

    def test_relationship_evidence_cli_extract_promote_review_query_and_compare(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            vector_db = root / "workspace" / "vectors" / "semantic_index.sqlite"
            seed_chunk(
                vector_db,
                "Acme Corp acquired Northstar Analytics. "
                "Beta Corp acquired Northstar Analytics. "
                "Acme Corp is led by Jamie Lee. "
                "Acme Corp is led by Priya Shah.",
            )

            extracted = run_praxis(root, "relationship-evidence", "extract")
            self.assertIn("chunks_scanned: 1", extracted.stdout)
            self.assertIn("candidates_written: 4", extracted.stdout)

            promoted = run_praxis(root, "relationship-evidence", "promote")
            self.assertIn("accepted: 3", promoted.stdout)
            self.assertIn("needs_review: 1", promoted.stdout)

            queried = run_praxis(root, "relationship-evidence", "query", "--subject", "Acme", "--predicate", "acquired")
            self.assertIn("# Graph relationships", queried.stdout)
            self.assertIn("object: Northstar Analytics", queried.stdout)
            self.assertIn("evidence: ann:", queried.stdout)

            compared = run_praxis(root, "relationship-evidence", "compare", "Acme Corp", "Beta Corp")
            self.assertIn("shared_relationships: 1", compared.stdout)
            self.assertIn("- acquired: Northstar Analytics", compared.stdout)

            review_list = run_praxis(root, "relationship-evidence", "review", "list")
            self.assertIn("cardinality_conflict", review_list.stdout)
            review_id = next(line.strip()[2:] for line in review_list.stdout.splitlines() if line.strip().startswith("- relationship-review:"))

            review_show = run_praxis(root, "relationship-evidence", "review", "show", review_id)
            self.assertIn("claim: Acme Corp --led_by-->", review_show.stdout)

            resolved = run_praxis(
                root,
                "relationship-evidence",
                "review",
                "resolve",
                review_id,
                "--resolution",
                "keep_existing_leader_pending_manual_review",
            )
            self.assertIn("status: resolved", resolved.stdout)

            empty_review = run_praxis(root, "relationship-evidence", "review", "list")
            self.assertIn("No relationship evidence review items found.", empty_review.stdout)


if __name__ == "__main__":
    unittest.main()
