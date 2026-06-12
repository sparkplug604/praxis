from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


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


def record_id_from(output: str) -> str:
    match = re.search(r"(adjudication:[a-f0-9]+)", output)
    if not match:
        raise AssertionError(f"No adjudication id in output:\n{output}")
    return match.group(1)


class AuthorityLayerTests(unittest.TestCase):
    def test_authority_init_compile_verify_and_anchor_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            initialized = run_praxis(root, "authority", "init")
            self.assertIn("status: ok", initialized.stdout)
            authority_root = root / "workspace" / "authority"
            self.assertTrue((authority_root / "bundles" / "default.json").exists())
            self.assertTrue((authority_root / "manifests" / "active.json").exists())

            compiled = run_praxis(root, "authority", "compile")
            self.assertIn("status: ok", compiled.stdout)
            self.assertIn("bundle_id: bundle:default", compiled.stdout)
            self.assertTrue((authority_root / "authority.sqlite").exists())

            verified = run_praxis(root, "authority", "verify", "--strict")
            self.assertIn("status: ok", verified.stdout)
            self.assertIn("ok: true", verified.stdout)

            anchors = run_praxis(root, "authority", "anchors", "list")
            self.assertIn("anchor:default:operational_metric", anchors.stdout)

            shown = run_praxis(root, "authority", "anchors", "show", "anchor:default:operational_metric")
            self.assertIn("authoritative_source: system_of_record", shown.stdout)
            self.assertIn("safe_default: ask_for_source_of_record", shown.stdout)

    def test_adjudication_blocks_forbidden_memory_and_warns_on_stale_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "authority", "init")
            run_praxis(root, "authority", "compile")

            fresh_at = datetime.now(timezone.utc).isoformat()
            allowed = run_praxis(
                root,
                "authority",
                "adjudicate",
                "--claim-type",
                "operational_metric",
                "--source",
                "system_of_record",
                "--evidence",
                "ev:test",
                "--fresh-at",
                fresh_at,
            )
            self.assertIn("decision: allow", allowed.stdout)
            self.assertIn("anchor_id: anchor:default:operational_metric", allowed.stdout)

            stale_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
            stale = run_praxis(
                root,
                "authority",
                "adjudicate",
                "--claim-type",
                "operational_metric",
                "--source",
                "system_of_record",
                "--evidence",
                "ev:test",
                "--fresh-at",
                stale_at,
            )
            self.assertIn("decision: warn", stale.stdout)
            self.assertIn("stale:", stale.stdout)

            forbidden = run_praxis(
                root,
                "authority",
                "adjudicate",
                "--claim-type",
                "operational_metric",
                "--source",
                "llm_summary",
                "--evidence",
                "ev:test",
                "--fresh-at",
                fresh_at,
                check=False,
            )
            self.assertEqual(3, forbidden.returncode)
            self.assertIn("decision: block", forbidden.stdout)
            self.assertIn("source is forbidden", forbidden.stdout)

            records = run_praxis(root, "authority", "records", "list")
            self.assertIn("operational_metric", records.stdout)
            self.assertIn("block", records.stdout)
            record = run_praxis(root, "authority", "records", "show", record_id_from(records.stdout))
            self.assertIn("decision:", record.stdout)
            self.assertIn("bundle_hash:", record.stdout)

    def test_custom_bundle_supports_client_specific_authority(self) -> None:
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
                                "forbidden_sources": ["google_ads"],
                                "freshness_sla_hours": 12,
                                "conflict_behavior": "block_on_conflict",
                                "required_evidence": ["evidence_id"],
                                "safe_default": "ask_for_hubspot_export",
                            }
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            activated = run_praxis(root, "authority", "activate", str(bundle_path))
            self.assertIn("status: ok", activated.stdout)
            run_praxis(root, "authority", "compile")

            blocked = run_praxis(
                root,
                "authority",
                "adjudicate",
                "--claim-type",
                "pipeline_metric",
                "--client",
                "acme",
                "--source",
                "google_ads",
                "--evidence",
                "ev:ads",
                "--fresh-at",
                datetime.now(timezone.utc).isoformat(),
                check=False,
            )
            self.assertEqual(3, blocked.returncode)
            self.assertIn("decision: block", blocked.stdout)
            self.assertIn("safe_default: ask_for_hubspot_export", blocked.stdout)

            unknown_client = run_praxis(
                root,
                "authority",
                "adjudicate",
                "--claim-type",
                "pipeline_metric",
                "--client",
                "other",
                "--source",
                "hubspot",
                "--evidence",
                "ev:hubspot",
                "--fresh-at",
                datetime.now(timezone.utc).isoformat(),
            )
            self.assertIn("decision: unknown", unknown_client.stdout)

    def test_compiled_inactive_bundle_does_not_leak_into_active_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "authority", "init")
            run_praxis(root, "authority", "compile")
            bundle_path = root / "workspace" / "authority" / "bundles" / "inactive-client.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "bundle_id": "bundle:inactive-client",
                        "version": 1,
                        "anchors": [
                            {
                                "id": "anchor:inactive:hubspot_pipeline",
                                "scope": {"claim_type": "pipeline_metric", "client_id": "acme"},
                                "authoritative_source": "hubspot",
                                "fallback_sources": [],
                                "forbidden_sources": ["google_ads"],
                                "freshness_sla_hours": 12,
                                "conflict_behavior": "block_on_conflict",
                                "required_evidence": ["evidence_id"],
                                "safe_default": "ask_for_hubspot_export",
                            }
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            run_praxis(root, "authority", "compile", "--bundle", str(bundle_path))

            anchors = run_praxis(root, "authority", "anchors", "list")
            self.assertIn("anchor:default:operational_metric", anchors.stdout)
            self.assertNotIn("anchor:inactive:hubspot_pipeline", anchors.stdout)

            result = run_praxis(
                root,
                "authority",
                "adjudicate",
                "--claim-type",
                "pipeline_metric",
                "--client",
                "acme",
                "--source",
                "hubspot",
                "--evidence",
                "ev:hubspot",
                "--fresh-at",
                datetime.now(timezone.utc).isoformat(),
            )
            self.assertIn("decision: unknown", result.stdout)
