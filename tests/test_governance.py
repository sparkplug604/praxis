from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from praxis.governance.doctor import blocking_governance_checks
from praxis.governance.evidence import EvidenceRef, evidence_has_active_status
from praxis.governance.models import GovernanceCheck


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


def write_reach_evidence(root: Path, *, evidence_id: str, source: str = "hubspot", client_id: str = "acme") -> None:
    evidence_dir = root / "workspace" / "reach" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_schema_version": 1,
        "evidence_id": evidence_id,
        "query_id": "pipeline_health",
        "client_id": client_id,
        "fresh_at": datetime.now(timezone.utc).isoformat(),
        "sources": [source],
        "source_links": [f"https://example.invalid/{source}/{client_id}"],
        "summary": "Fixture source-of-record evidence for pipeline health.",
        "metrics": {"pipeline_value": 1000},
        "metric_sources": {"pipeline_value": source},
        "source_metadata": {"connector": source},
        "freshness_status": "fresh",
        "connector_versions": {source: "fixture"},
        "conflicts": [],
        "conflict_records": [],
        "metric_lineage": {},
        "partial_data": False,
        "data_quality_status": "ok",
        "confidence_score": 1.0,
        "warnings": [],
        "query_hash": "fixture",
    }
    (evidence_dir / "pipeline_health.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


class GovernanceLayerTests(unittest.TestCase):
    def test_governance_blocks_missing_evidence_and_verifies_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            init = run_praxis(root, "governance", "init")
            self.assertIn("status: ok", init.stdout)

            missing = run_praxis(
                root,
                "governance",
                "evaluate",
                "--claim-type",
                "operational_metric",
                "--evidence",
                "ev:missing",
                check=False,
            )
            self.assertEqual(3, missing.returncode)
            self.assertIn("decision: block", missing.stdout)
            self.assertIn("evidence_exists: false", missing.stdout)

            second_missing = run_praxis(
                root,
                "governance",
                "evaluate",
                "--claim-type",
                "operational_metric",
                "--evidence",
                "ev:also-missing",
                check=False,
            )
            self.assertEqual(3, second_missing.returncode)

            events = run_praxis(root, "governance", "events", "list")
            self.assertIn("policy_evaluation", events.stdout)

            ledger = run_praxis(root, "governance", "ledger", "verify")
            self.assertIn("ok: true", ledger.stdout)

    def test_governance_allows_fresh_authoritative_reach_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "authority", "init")
            bundle_path = root / "workspace" / "authority" / "bundles" / "client.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "bundle_id": "bundle:client",
                        "version": 1,
                        "anchors": [
                            {
                                "id": "anchor:client:hubspot_pipeline",
                                "scope": {"claim_type": "pipeline_metric", "client_id": "acme"},
                                "authoritative_source": "hubspot",
                                "fallback_sources": ["evidence_card"],
                                "forbidden_sources": ["llm_summary", "provisional_memory"],
                                "freshness_sla_hours": 24,
                                "conflict_behavior": "block_on_conflict",
                                "required_evidence": ["evidence_id"],
                                "safe_default": "ask_for_hubspot",
                            }
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            run_praxis(root, "authority", "activate", str(bundle_path))
            run_praxis(root, "authority", "compile")
            write_reach_evidence(root, evidence_id="ev:pipeline:acme:1")

            result = run_praxis(
                root,
                "governance",
                "evaluate",
                "--claim-type",
                "pipeline_metric",
                "--client",
                "acme",
                "--source",
                "hubspot",
                "--evidence",
                "ev:pipeline:acme:1",
            )
            self.assertIn("decision: allow", result.stdout)
            self.assertIn("authority_decision: allow", result.stdout)
            self.assertIn("evidence_kind: reach_evidence", result.stdout)

            doctor = run_praxis(root, "governance", "doctor", "--init")
            self.assertIn("governance.ledger: ok", doctor.stdout)
            self.assertIn("governance.authority: ok", doctor.stdout)

    def test_governance_warns_on_conflicted_reach_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "authority", "init")
            run_praxis(root, "authority", "compile")
            write_reach_evidence(root, evidence_id="ev:conflicted")
            evidence_path = root / "workspace" / "reach" / "evidence" / "pipeline_health.json"
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            payload["data_quality_status"] = "conflicted"
            payload["conflict_records"] = [{"id": "reach-conflict:fixture"}]
            evidence_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            result = run_praxis(
                root,
                "governance",
                "evaluate",
                "--claim-type",
                "operational_metric",
                "--source",
                "evidence_card",
                "--evidence",
                "ev:conflicted",
            )
            self.assertIn("decision: warn", result.stdout)
            self.assertIn("conflict_count: 1", result.stdout)
            self.assertIn("evidence status is not active", result.stdout)

    def test_governance_threshold_can_warn_or_error_gate(self) -> None:
        checks = [
            GovernanceCheck(
                check_id="ledger",
                severity="ok",
                status="ok",
                summary="ok",
            ),
            GovernanceCheck(
                check_id="authority",
                severity="warn",
                status="not_configured",
                summary="authority anchors are not configured",
            ),
        ]
        self.assertEqual(["authority"], [check.check_id for check in blocking_governance_checks(checks)])
        self.assertEqual([], blocking_governance_checks(checks, threshold="error"))

    def test_unknown_evidence_status_is_not_assumed_active(self) -> None:
        self.assertFalse(evidence_has_active_status(EvidenceRef(evidence_id="ev:test", exists=True, status="provisional")))
        self.assertFalse(evidence_has_active_status(EvidenceRef(evidence_id="ev:test", exists=True, status="needs_review")))
        self.assertTrue(evidence_has_active_status(EvidenceRef(evidence_id="ev:test", exists=True, status="active")))


if __name__ == "__main__":
    unittest.main()
