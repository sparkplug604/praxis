from __future__ import annotations

import os
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from praxis.reach.connectors.bigquery import BigQueryConnector
from praxis.reach.connectors.bigquery_client import BigQueryRows
from praxis.reach.connectors.google_ads import GoogleAdsConnector
from praxis.reach.connectors.google_ads_client import GoogleAdsRows
from praxis.reach.connectors.google_analytics import GoogleAnalyticsConnector
from praxis.reach.connectors.google_analytics_client import GoogleAnalyticsReport
from praxis.reach.connectors.hubspot import HubSpotConnector
from praxis.reach.connectors.hubspot_client import HubSpotClient
from praxis.reach.evidence import compute_query_hash
from praxis.reach.manifests import load_manifest
from praxis.reach.models import ClientCapsule, default_systems
from praxis.reach.ontology import default_field_map, default_metric_definitions
from praxis.reach.storage import read_json, write_json


REPO = Path(__file__).resolve().parents[1]


def copy_fixture(source: str, root: Path) -> None:
    src = REPO / source
    dst = root / source
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


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


def evidence_id_from(output: str) -> str:
    match = re.search(r"evidence_id:\s*(ev:[^\s]+)", output)
    if not match:
        raise AssertionError(f"No evidence_id found in output:\n{output}")
    return match.group(1)


class ReachAgencyTests(unittest.TestCase):
    def test_agency_client_capsule_and_reach_query_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            init = run_praxis(root, "reach", "init")
            self.assertIn("status: ok", init.stdout)
            doctor = run_praxis(root, "reach", "doctor")
            self.assertIn("ok: connectors:", doctor.stdout)

            created = run_praxis(
                root,
                "agency",
                "client",
                "create",
                "Acme",
                "--name",
                "Acme SaaS",
                "--timezone",
                "America/Toronto",
                "--currency",
                "CAD",
            )
            self.assertIn("client_id: acme", created.stdout)
            self.assertTrue((root / "agency" / "clients" / "acme" / "systems.json").exists())
            self.assertTrue((root / "agency" / "clients" / "acme" / "field_map.json").exists())
            self.assertTrue((root / "agency" / "clients" / "acme" / "metrics.json").exists())
            self.assertTrue((root / "agency" / "clients" / "acme" / "permissions.json").exists())

            listed = run_praxis(root, "agency", "client", "list")
            self.assertIn("acme: Acme SaaS", listed.stdout)
            self.assertIn("mock_ads", listed.stdout)
            self.assertIn("mock_crm", listed.stdout)

            query_list = run_praxis(root, "reach", "query", "list")
            self.assertIn("weekly_gtm_review", query_list.stdout)

            query = run_praxis(root, "reach", "query", "run", "weekly_gtm_review", "--client", "acme", "--days", "30")
            evidence_id = evidence_id_from(query.stdout)
            self.assertIn("storage_level: aggregate_summary", query.stdout)
            evidence_payload = json.loads(next((root / "reach" / "evidence").glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(1, evidence_payload["artifact_schema_version"])
            self.assertEqual(44, evidence_payload["metrics"]["leads"])
            self.assertEqual("mock_crm", evidence_payload["metric_sources"]["leads"])
            self.assertEqual("mock_crm", evidence_payload["metric_lineage"]["leads"]["selected_provider"])
            self.assertFalse(evidence_payload["partial_data"])
            self.assertEqual("conflicted", evidence_payload["data_quality_status"])
            self.assertLess(evidence_payload["confidence_score"], 1.0)
            self.assertTrue(evidence_payload["conflict_records"])
            self.assertTrue(list((root / "reach" / "conflicts").glob("*.json")))
            self.assertIn("start_date", evidence_payload["params"])
            self.assertIn("end_date", evidence_payload["params"])
            self.assertIn("source_metadata", evidence_payload)
            manifest = load_manifest(root, "weekly_gtm_review")
            self.assertEqual(
                compute_query_hash(manifest, dict(reversed(list(evidence_payload["params"].items())))),
                evidence_payload["query_hash"],
            )

            shown = run_praxis(root, "reach", "evidence", "show", evidence_id)
            self.assertIn("Mock CRM found", shown.stdout)
            self.assertIn("Mock ads reported", shown.stdout)
            self.assertIn("Ad-platform lead counts are directional", shown.stdout)
            self.assertIn("crm_vs_ad_leads", shown.stdout)

            context = run_praxis(root, "reach", "context", "build", "weekly_gtm_review", "--client", "acme")
            self.assertIn("context_pack:", context.stdout)
            context_path = Path(context.stdout.split("context_pack:", 1)[1].strip())
            self.assertTrue(context_path.exists())
            self.assertIn("Source Links", context_path.read_text(encoding="utf-8"))

            stale = run_praxis(root, "reach", "stale", "list", "--client", "acme", "--all")
            self.assertIn("status: fresh", stale.stdout)

            refreshed = run_praxis(root, "reach", "evidence", "refresh", evidence_id)
            self.assertIn("evidence_id:", refreshed.stdout)
            self.assertNotEqual(evidence_id, evidence_id_from(refreshed.stdout))
            refreshed_context = run_praxis(root, "reach", "context", "build", "weekly_gtm_review", "--client", "acme")
            refreshed_context_path = Path(refreshed_context.stdout.split("context_pack:", 1)[1].strip())
            self.assertNotEqual(context_path, refreshed_context_path)
            self.assertTrue(context_path.exists())
            self.assertTrue(refreshed_context_path.exists())

            evidence_files = sorted((root / "reach" / "evidence").glob("*.json"))
            self.assertGreaterEqual(len(evidence_files), 2)

            stale_file = evidence_files[0]
            payload = json.loads(stale_file.read_text(encoding="utf-8"))
            payload["fresh_at"] = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
            stale_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            stale_result = run_praxis(root, "reach", "stale", "list", "--client", "acme")
            self.assertIn("status: stale", stale_result.stdout)
            stale_show = run_praxis(root, "reach", "evidence", "show", payload["evidence_id"])
            self.assertIn("freshness_status: stale", stale_show.stdout)

    def test_mapping_metrics_and_core_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            copy_fixture("kg/schema.sql", root)
            copy_fixture("kg/seed_graph.json", root)
            copy_fixture("db/schema.sql", root)
            run_praxis(root, "reach", "init")
            run_praxis(root, "agency", "client", "create", "acme")

            mapped = run_praxis(
                root,
                "agency",
                "client",
                "map-fields",
                "acme",
                "--object",
                "opportunity",
                "--field",
                "amount",
                "--source-field",
                "properties.amount",
            )
            self.assertIn("properties.amount", mapped.stdout)

            bad_map = run_praxis(
                root,
                "agency",
                "client",
                "map-fields",
                "acme",
                "--object",
                "opportunity",
                "--field",
                "amount",
                check=False,
            )
            self.assertEqual(2, bad_map.returncode)
            self.assertIn("--field and --source-field must be provided together", bad_map.stdout)

            metric = run_praxis(
                root,
                "agency",
                "client",
                "define-metric",
                "acme",
                "mqls",
                "--canonical-object",
                "contact",
                "--description",
                "Marketing qualified leads",
                "--source-priority",
                "crm",
                "--definition",
                "lifecycle_stage == marketingqualifiedlead",
            )
            self.assertIn("status: updated", metric.stdout)

            query = run_praxis(root, "reach", "query", "run", "pipeline_health", "--client", "acme")
            evidence_id = evidence_id_from(query.stdout)
            captured = run_praxis(root, "reach", "evidence", "capture", evidence_id)
            self.assertIn("capture_id:", captured.stdout)
            self.assertTrue((root / "reach" / "evidence_sources").exists())

            doctor = run_praxis(root, "agency", "client", "doctor", "acme")
            self.assertIn("status: ok", doctor.stdout)

            dated = run_praxis(
                root,
                "reach",
                "query",
                "run",
                "pipeline_health",
                "--client",
                "acme",
                "--start-date",
                "2026-01-01",
                "--end-date",
                "2026-01-31",
            )
            dated_evidence_id = evidence_id_from(dated.stdout)
            dated_payload = next(
                payload
                for payload in (
                    json.loads(path.read_text(encoding="utf-8"))
                    for path in (root / "reach" / "evidence").glob("*.json")
                )
                if payload["evidence_id"] == dated_evidence_id
            )
            self.assertEqual("2026-01-01", dated_payload["params"]["start_date"])
            self.assertEqual("2026-01-31", dated_payload["params"]["end_date"])

            missing_date = run_praxis(
                root,
                "reach",
                "query",
                "run",
                "pipeline_health",
                "--client",
                "acme",
                "--start-date",
                "2026-01-01",
                check=False,
            )
            self.assertEqual(2, missing_date.returncode)
            self.assertIn("--start-date and --end-date must be provided together", missing_date.stdout)

    def test_fixture_connectors_and_agency_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "reach", "init")
            run_praxis(root, "agency", "client", "create", "acme", "--crm", "fixture_crm", "--ads", "fixture_ads")
            fixture_dir = root / "reach" / "fixtures" / "acme"
            fixture_dir.mkdir(parents=True, exist_ok=True)
            (fixture_dir / "fixture_crm.json").write_text(
                json.dumps(
                    {
                        "summary": "Fixture CRM reports strong pipeline.",
                        "metrics": {"leads": 88, "opportunities": 17, "pipeline_amount": 125000},
                        "source_links": ["fixture://acme/crm"],
                        "row_count": 105,
                    }
                ),
                encoding="utf-8",
            )
            (fixture_dir / "fixture_ads.json").write_text(
                json.dumps(
                    {
                        "summary": "Fixture ads reports falling reach.",
                            "metrics": {"spend": 21000, "reach": 62000, "impressions": 140000, "clicks": 4200, "leads": 101},
                        "source_links": ["fixture://acme/ads"],
                        "warnings": ["Fixture reach is down 18%."],
                        "conflicts": ["crm_vs_ad_leads"],
                        "row_count": 90,
                    }
                ),
                encoding="utf-8",
            )

            run = run_praxis(root, "agency", "run", "weekly_gtm_review", "--all-clients", "--context")
            self.assertIn("client_id: acme", run.stdout)
            self.assertIn("context_pack:", run.stdout)
            evidence = run_praxis(root, "reach", "evidence", "list", "--client", "acme")
            self.assertIn("weekly_gtm_review", evidence.stdout)
            shown = run_praxis(root, "reach", "evidence", "show", evidence_id_from(run.stdout))
            self.assertIn("Fixture CRM reports strong pipeline", shown.stdout)
            self.assertIn("crm_vs_ad_leads", shown.stdout)
            self.assertIn("Conflict Records", shown.stdout)

            ambiguous = run_praxis(
                root,
                "agency",
                "run",
                "weekly_gtm_review",
                "--all-clients",
                "--clients",
                "acme",
                check=False,
            )
            self.assertEqual(2, ambiguous.returncode)
            self.assertIn("Use either --all-clients or --clients", ambiguous.stdout)

    def test_agency_run_can_report_per_client_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "reach", "init")
            run_praxis(root, "agency", "client", "create", "acme")
            run_praxis(root, "agency", "client", "create", "beta", "--crm", "hubspot", "--ads", "mock_ads")

            result = run_praxis(
                root,
                "agency",
                "run",
                "weekly_gtm_review",
                "--all-clients",
                "--continue-on-error",
                "--context",
                check=False,
            )
            self.assertEqual(1, result.returncode)
            self.assertIn("client_id: acme", result.stdout)
            self.assertIn("status: ok", result.stdout)
            self.assertIn("client_id: beta", result.stdout)
            self.assertIn("status: error", result.stdout)
            self.assertIn("HubSpot connector requires HUBSPOT_BETA_ACCESS_TOKEN", result.stdout)
            self.assertNotIn("Traceback", result.stdout)

    def test_client_doctor_flags_unconfigured_connector(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "reach", "init")
            run_praxis(root, "agency", "client", "create", "broken", "--crm", "unknown_crm")
            result = run_praxis(root, "agency", "client", "doctor", "broken", check=False)
            self.assertEqual(1, result.returncode)
            self.assertIn("unknown_crm: no installed connector", result.stdout)
            reach_doctor = run_praxis(root, "reach", "doctor", check=False)
            self.assertEqual(1, reach_doctor.returncode)
            self.assertIn("broken: unknown_crm: no installed connector", reach_doctor.stdout)

    def test_fixture_generator_creates_demo_client(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "reach", "init")
            created = run_praxis(root, "agency", "fixture", "create", "demo", "--profile", "b2b-saas")
            self.assertIn("status: created", created.stdout)
            self.assertTrue((root / "reach" / "fixtures" / "demo" / "fixture_crm.json").exists())
            run = run_praxis(root, "agency", "run", "weekly_gtm_review", "--all-clients", "--context")
            self.assertIn("client_id: demo", run.stdout)
            report = run_praxis(root, "agency", "stale-context-report", "--all")
            self.assertIn("demo: fresh", report.stdout)

    def test_setup_wizard_runs_non_interactive_reach_demo(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            result = run_praxis(root, "setup", "--non-interactive", "--path", "reach-demo")
            self.assertIn("Reach demo is ready", result.stdout)
            self.assertTrue((root / "agency" / "clients" / "demo" / "client.json").exists())
            self.assertTrue(any((root / "reach" / "evidence").glob("*.json")))
            self.assertTrue(any((root / "reach" / "context_packs").glob("**/*.md")))

            missing_path = run_praxis(root, "setup", "--non-interactive", check=False)
            self.assertEqual(2, missing_path.returncode)
            self.assertIn("--non-interactive requires --path", missing_path.stdout)

    def test_demo_command_runs_reach_and_agency_fixture_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            listed = run_praxis(root, "demo")
            self.assertIn("praxis demo core", listed.stdout)

            for fixture in ("db/schema.sql", "kg/schema.sql", "kg/seed_graph.json", "sources/seed_sources.json"):
                copy_fixture(fixture, root)
            core = run_praxis(root, "demo", "core")
            self.assertIn("Core demo complete", core.stdout)
            self.assertTrue((root / "research" / "demo_sources" / "praxis-core-demo.md").exists())

            reach = run_praxis(root, "demo", "reach")
            self.assertIn("Reach demo complete", reach.stdout)
            self.assertTrue(any((root / "reach" / "evidence").glob("*.json")))

            agency = run_praxis(root, "demo", "agency")
            self.assertIn("Agency demo complete", agency.stdout)
            self.assertTrue((root / "agency" / "clients" / "acme" / "client.json").exists())
            self.assertTrue((root / "agency" / "clients" / "beta" / "client.json").exists())

    def test_unconfigured_real_connector_is_reported_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "agency", "client", "create", "beta", "--crm", "hubspot", "--ads", "mock_ads")

            result = run_praxis(root, "reach", "query", "run", "pipeline_health", "--client", "beta", check=False)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("HubSpot connector requires HUBSPOT_BETA_ACCESS_TOKEN", result.stdout)
            self.assertNotIn("Traceback", result.stdout)

            test = run_praxis(root, "reach", "connectors", "test", "hubspot", "--client", "beta", check=False)
            self.assertEqual(1, test.returncode)
            self.assertIn("status: missing_credentials", test.stdout)
            self.assertIn("HUBSPOT_BETA_ACCESS_TOKEN", test.stdout)

    def test_google_ads_connector_reports_per_client_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "reach", "init")
            run_praxis(root, "agency", "client", "create", "acme", "--crm", "mock_crm", "--ads", "google_ads")

            shown = run_praxis(root, "agency", "client", "show", "acme")
            self.assertIn("google_ads", shown.stdout)
            config = json.loads((root / "agency" / "clients" / "acme" / "systems.json").read_text(encoding="utf-8"))
            ads_config = config["systems"]["ads"][0]
            self.assertEqual("GOOGLE_ADS_ACME_CONFIGURATION_FILE", ads_config["config_env"])
            self.assertEqual("GOOGLE_ADS_ACME_CUSTOMER_ID", ads_config["customer_id_env"])

            test = run_praxis(root, "reach", "connectors", "test", "google_ads", "--client", "acme", check=False)
            self.assertEqual(1, test.returncode)
            self.assertIn("status: missing_configuration", test.stdout)
            self.assertIn("GOOGLE_ADS_ACME_CONFIGURATION_FILE", test.stdout)
            self.assertIn("GOOGLE_ADS_ACME_CUSTOMER_ID", test.stdout)

    def test_bigquery_connector_reports_per_client_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "reach", "init")
            run_praxis(root, "agency", "client", "create", "acme", "--crm", "mock_crm", "--ads", "mock_ads", "--warehouse", "bigquery")

            shown = run_praxis(root, "agency", "client", "show", "acme")
            self.assertIn("bigquery", shown.stdout)
            config = json.loads((root / "agency" / "clients" / "acme" / "systems.json").read_text(encoding="utf-8"))
            warehouse_config = config["systems"]["warehouse"]
            self.assertEqual("BIGQUERY_ACME_PROJECT_ID", warehouse_config["project_id_env"])
            self.assertEqual("BIGQUERY_ACME_DATASET", warehouse_config["dataset_env"])
            self.assertIn("contacts", warehouse_config["allowed_tables"])

            query_list = run_praxis(root, "reach", "query", "list")
            self.assertIn("warehouse_segment_size_preview", query_list.stdout)

            test = run_praxis(root, "reach", "connectors", "test", "bigquery", "--client", "acme", check=False)
            self.assertEqual(1, test.returncode)
            self.assertIn("status: missing_configuration", test.stdout)
            self.assertIn("BIGQUERY_ACME_PROJECT_ID", test.stdout)
            self.assertIn("BIGQUERY_ACME_DATASET", test.stdout)

    def test_bigquery_connector_runs_segment_size_preview_with_fake_client(self) -> None:
        calls = []

        class FakeBigQueryClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

            def dry_run(self, query, *, parameters=None, maximum_bytes_billed=None, labels=None):
                calls.append({"kind": "dry_run", "query": query, "parameters": parameters or {}, "maximum_bytes_billed": maximum_bytes_billed, "labels": labels, "kwargs": self.kwargs})
                return {"job_id": "dry-job", "total_bytes_processed": 12_345}

            def query(self, query, *, parameters=None, maximum_bytes_billed=None, labels=None):
                calls.append({"kind": "query", "query": query, "parameters": parameters or {}, "maximum_bytes_billed": maximum_bytes_billed, "labels": labels, "kwargs": self.kwargs})
                return BigQueryRows(
                    rows=[
                        {
                            "contacts": 1500,
                            "accounts": 82,
                            "segment_size": 1500,
                            "suppressed_count": 37,
                            "missing_email_count": 12,
                        }
                    ],
                    row_count=1,
                    metadata={"job_id": "query-job", "total_bytes_processed": 12_345, "cache_hit": False},
                )

        capsule = ClientCapsule(
            client_id="acme",
            name="Acme",
            systems=default_systems(crm="mock_crm", ads="mock_ads", warehouse="bigquery", client_id="acme"),
            metrics=default_metric_definitions(),
            field_map=default_field_map(crm="mock_crm", ads="mock_ads"),
        )
        manifest = load_manifest(Path(tempfile.mkdtemp()), "warehouse_segment_size_preview")
        os.environ["BIGQUERY_ACME_PROJECT_ID"] = "acme-prod"
        os.environ["BIGQUERY_ACME_DATASET"] = "gtm_mart"
        try:
            result = BigQueryConnector(client_factory=FakeBigQueryClient).run_query(capsule, manifest, {"client_id": "acme"})
        finally:
            os.environ.pop("BIGQUERY_ACME_PROJECT_ID", None)
            os.environ.pop("BIGQUERY_ACME_DATASET", None)

        self.assertEqual(1500, result.metrics["contacts"])
        self.assertEqual(82, result.metrics["accounts"])
        self.assertEqual(37, result.metrics["suppressed_count"])
        self.assertEqual("aggregate_summary", result.storage_level)
        self.assertEqual("none", result.metadata["row_storage"])
        self.assertEqual(12_345, result.metadata["dry_run_bytes_estimate"])
        self.assertEqual(["acme-prod.gtm_mart.contacts"], result.metadata["tables_referenced"])
        self.assertIn("FROM `acme-prod.gtm_mart.contacts`", calls[0]["query"])
        self.assertEqual("acme", calls[0]["labels"]["praxis_client"])
        self.assertEqual(1_000_000_000, calls[0]["maximum_bytes_billed"])

    def test_bigquery_connector_runs_buyer_signal_rollup_and_discovery(self) -> None:
        class FakeBigQueryClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

            def dry_run(self, query, *, parameters=None, maximum_bytes_billed=None, labels=None):
                return {"job_id": "dry-job", "total_bytes_processed": 123}

            def query(self, query, *, parameters=None, maximum_bytes_billed=None, labels=None):
                self.query_call = {"query": query, "parameters": parameters or {}, "labels": labels or {}}
                return BigQueryRows(
                    rows=[{"buyer_signal_count": 24, "avg_signal_strength": 0.73, "accounts": 11, "contacts": 19}],
                    row_count=1,
                    metadata={"job_id": "query-job", "total_bytes_processed": 456},
                )

            def list_tables(self, *, project_id, dataset, include_columns=False):
                return [{"kind": "table", "id": "buyer_signals", "resource_name": f"{project_id}.{dataset}.buyer_signals"}]

        capsule = ClientCapsule(
            client_id="acme",
            name="Acme",
            systems=default_systems(crm="mock_crm", ads="mock_ads", warehouse="bigquery", client_id="acme"),
            metrics=default_metric_definitions(),
            field_map=default_field_map(crm="mock_crm", ads="mock_ads"),
        )
        connector = BigQueryConnector(client_factory=FakeBigQueryClient)
        os.environ["BIGQUERY_ACME_PROJECT_ID"] = "acme-prod"
        os.environ["BIGQUERY_ACME_DATASET"] = "gtm_mart"
        try:
            setup = connector.check_setup(capsule, live=True)
            discovered = connector.discover_resources(capsule, live=True)
            result = connector.run_query(
                capsule,
                load_manifest(Path(tempfile.mkdtemp()), "warehouse_buyer_signal_rollup"),
                {"client_id": "acme", "start_date": "2026-01-01", "end_date": "2026-01-31"},
            )
        finally:
            os.environ.pop("BIGQUERY_ACME_PROJECT_ID", None)
            os.environ.pop("BIGQUERY_ACME_DATASET", None)

        self.assertEqual("ok", setup.status)
        self.assertTrue(any(resource.get("kind") == "table" for resource in discovered.resources))
        self.assertEqual(24, result.metrics["buyer_signal_count"])
        self.assertEqual(0.73, result.metrics["avg_signal_strength"])
        self.assertEqual(11, result.metrics["accounts"])
        self.assertIn("buyer_signals", result.summary)
        self.assertIn("start_date", result.metadata["query_parameters"])

    def test_bigquery_connector_blocks_queries_above_budget(self) -> None:
        class ExpensiveBigQueryClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

            def dry_run(self, query, *, parameters=None, maximum_bytes_billed=None, labels=None):
                return {"job_id": "dry-job", "total_bytes_processed": 10_000}

            def query(self, query, *, parameters=None, maximum_bytes_billed=None, labels=None):  # pragma: no cover - should not execute.
                raise AssertionError("query should not run after over-budget dry run")

        systems = default_systems(crm="mock_crm", ads="mock_ads", warehouse="bigquery", client_id="acme")
        systems["warehouse"]["max_bytes_billed"] = 100
        capsule = ClientCapsule(
            client_id="acme",
            name="Acme",
            systems=systems,
            metrics=default_metric_definitions(),
            field_map=default_field_map(crm="mock_crm", ads="mock_ads"),
        )
        manifest = load_manifest(Path(tempfile.mkdtemp()), "warehouse_segment_size_preview")
        os.environ["BIGQUERY_ACME_PROJECT_ID"] = "acme-prod"
        os.environ["BIGQUERY_ACME_DATASET"] = "gtm_mart"
        try:
            with self.assertRaisesRegex(RuntimeError, "above max_bytes_billed"):
                BigQueryConnector(client_factory=ExpensiveBigQueryClient).run_query(capsule, manifest, {"client_id": "acme"})
        finally:
            os.environ.pop("BIGQUERY_ACME_PROJECT_ID", None)
            os.environ.pop("BIGQUERY_ACME_DATASET", None)

    def test_google_ads_connector_aggregates_streamed_campaign_metrics(self) -> None:
        calls = []

        class FakeGoogleAdsReachClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

            def search_stream(self, *, customer_id: str, query: str, max_batches: int):
                calls.append({"customer_id": customer_id, "query": query, "max_batches": max_batches, "kwargs": self.kwargs})
                return GoogleAdsRows(
                    rows=[
                        {
                            "metrics": {
                                "cost_micros": 1_250_000,
                                "impressions": 100,
                                "clicks": 10,
                                "conversions": 1.5,
                                "conversions_value": 30,
                            }
                        },
                        {
                            "metrics": {
                                "cost_micros": 1_750_000,
                                "impressions": 200,
                                "clicks": 20,
                                "conversions": 2,
                                "conversions_value": 50,
                            }
                        },
                    ],
                    batches_read=2,
                )

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            capsule = ClientCapsule(
                client_id="acme",
                name="Acme",
                systems=default_systems(crm="mock_crm", ads="google_ads", client_id="acme"),
                metrics=default_metric_definitions(),
                field_map=default_field_map(crm="mock_crm", ads="google_ads"),
            )
            manifest = load_manifest(root, "reach_historical")
            os.environ["GOOGLE_ADS_ACME_CONFIGURATION_FILE"] = "/tmp/google-ads.yaml"
            os.environ["GOOGLE_ADS_ACME_CUSTOMER_ID"] = "123-456-7890"
            try:
                result = GoogleAdsConnector(client_factory=FakeGoogleAdsReachClient).run_query(
                    capsule,
                    manifest,
                    {"client_id": "acme", "start_date": "2026-01-01", "end_date": "2026-01-31"},
                )
            finally:
                os.environ.pop("GOOGLE_ADS_ACME_CONFIGURATION_FILE", None)
                os.environ.pop("GOOGLE_ADS_ACME_CUSTOMER_ID", None)

        self.assertEqual(3.0, result.metrics["spend"])
        self.assertEqual(300, result.metrics["impressions"])
        self.assertEqual(30, result.metrics["clicks"])
        self.assertEqual(3.5, result.metrics["conversions"])
        self.assertEqual(80.0, result.metrics["conversion_value"])
        self.assertEqual(0.1167, result.metrics["conversion_rate"])
        self.assertEqual("1234567890", calls[0]["customer_id"])
        self.assertIn("segments.date BETWEEN '2026-01-01' AND '2026-01-31'", calls[0]["query"])
        self.assertEqual("none", result.metadata["row_storage"])

    def test_google_ads_discovery_and_conversion_mapping(self) -> None:
        class FakeGoogleAdsReachClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

            def list_accessible_customers(self):
                return ["customers/1112223333"]

            def list_customer_clients(self, manager_customer_id: str):
                return [
                    {
                        "kind": "manager_child",
                        "id": "1234567890",
                        "resource_name": "customers/1234567890",
                        "name": "Acme Ads",
                        "manager": False,
                    }
                ]

            def search_stream(self, *, customer_id: str, query: str, max_batches: int):
                if "segments.conversion_action_name" in query:
                    return GoogleAdsRows(
                        rows=[
                            {"segments": {"conversion_action_name": "Lead Form Submit"}, "metrics": {"conversions": 4, "conversions_value": 100}},
                            {"segments": {"conversion_action_name": "Newsletter Signup"}, "metrics": {"conversions": 20, "conversions_value": 5}},
                        ],
                        batches_read=1,
                    )
                return GoogleAdsRows(
                    rows=[
                        {"metrics": {"cost_micros": 5_000_000, "impressions": 1000, "clicks": 100, "conversions": 24, "conversions_value": 105}}
                    ],
                    batches_read=1,
                )

        capsule = ClientCapsule(
            client_id="acme",
            name="Acme",
            systems=default_systems(crm="mock_crm", ads="google_ads", client_id="acme"),
            metrics={
                **default_metric_definitions(),
                "conversion_definitions": {
                    "lead_form": {
                        "source": "google_ads",
                        "source_name": "Lead Form Submit",
                        "canonical_metric": "conversions",
                    }
                },
            },
            field_map=default_field_map(crm="mock_crm", ads="google_ads"),
        )
        connector = GoogleAdsConnector(client_factory=FakeGoogleAdsReachClient)
        os.environ["GOOGLE_ADS_ACME_CONFIGURATION_FILE"] = "/tmp/google-ads.yaml"
        os.environ["GOOGLE_ADS_ACME_CUSTOMER_ID"] = "1234567890"
        os.environ["GOOGLE_ADS_ACME_LOGIN_CUSTOMER_ID"] = "1112223333"
        try:
            live = connector.check_setup(capsule, live=True)
            discovered = connector.discover_resources(capsule, live=True)
            result = connector.run_query(
                capsule,
                load_manifest(Path(tempfile.mkdtemp()), "reach_historical"),
                {"client_id": "acme", "start_date": "2026-01-01", "end_date": "2026-01-31"},
            )
        finally:
            os.environ.pop("GOOGLE_ADS_ACME_CONFIGURATION_FILE", None)
            os.environ.pop("GOOGLE_ADS_ACME_CUSTOMER_ID", None)
            os.environ.pop("GOOGLE_ADS_ACME_LOGIN_CUSTOMER_ID", None)

        self.assertEqual("ok", live.status)
        self.assertTrue(any(resource.get("kind") == "manager_child" for resource in discovered.resources))
        self.assertEqual(4, result.metrics["conversions"])
        self.assertEqual(100.0, result.metrics["conversion_value"])
        self.assertEqual(0.04, result.metrics["conversion_rate"])
        self.assertEqual(1, result.metadata["conversion_mapping"]["ignored_rows"])
        self.assertIn("google_ads:Lead Form Submit->conversions", result.metadata["conversion_definitions"])

    def test_google_analytics_client_capsule_and_connector_metrics(self) -> None:
        class FakeGoogleAnalyticsClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

            def run_report(self, *, property_id, metrics, dimensions, start_date, end_date, limit):
                self.request = {
                    "property_id": property_id,
                    "metrics": metrics,
                    "dimensions": dimensions,
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": limit,
                }
                return GoogleAnalyticsReport(
                    rows=[
                        {
                            "metrics": {
                                "sessions": 100,
                                "activeUsers": 40,
                                "totalUsers": 45,
                                "eventCount": 800,
                                "keyEvents": 8,
                                "purchaseRevenue": 1200.25,
                                "engagementRate": 0.61,
                            }
                        }
                    ],
                    row_count=1,
                    metadata={"property_quota": {"tokens_per_day": {"remaining": 8}}},
                )

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "reach", "init")
            created = run_praxis(
                root,
                "agency",
                "client",
                "create",
                "acme",
                "--crm",
                "mock_crm",
                "--ads",
                "mock_ads",
                "--analytics",
                "google_analytics",
            )
            self.assertIn("client_id: acme", created.stdout)
            shown = run_praxis(root, "agency", "client", "show", "acme")
            self.assertIn("google_analytics", shown.stdout)
            query_list = run_praxis(root, "reach", "query", "list")
            self.assertIn("website_performance", query_list.stdout)

            capsule = ClientCapsule(
                client_id="acme",
                name="Acme",
                systems=default_systems(crm="mock_crm", ads="mock_ads", analytics="google_analytics", client_id="acme"),
                metrics=default_metric_definitions(analytics="google_analytics"),
                field_map=default_field_map(crm="mock_crm", ads="mock_ads", analytics="google_analytics"),
            )
            manifest = load_manifest(root, "website_performance")
            os.environ["GOOGLE_ANALYTICS_ACME_PROPERTY_ID"] = "123456"
            try:
                result = GoogleAnalyticsConnector(client_factory=FakeGoogleAnalyticsClient).run_query(
                    capsule,
                    manifest,
                    {"client_id": "acme", "start_date": "2026-01-01", "end_date": "2026-01-31"},
                )
            finally:
                os.environ.pop("GOOGLE_ANALYTICS_ACME_PROPERTY_ID", None)

        self.assertEqual(100, result.metrics["sessions"])
        self.assertEqual(40, result.metrics["active_users"])
        self.assertEqual(800, result.metrics["event_count"])
        self.assertEqual(8, result.metrics["key_events"])
        self.assertEqual(8, result.metrics["conversions"])
        self.assertEqual(1200.25, result.metrics["revenue"])
        self.assertEqual(0.61, result.metrics["engagement_rate"])
        self.assertEqual(0.08, result.metrics["conversion_rate"])
        self.assertEqual("none", result.metadata["row_storage"])
        self.assertIn("GA4 quota is low", " ".join(result.warnings))

    def test_google_analytics_discovery_and_conversion_mapping(self) -> None:
        class FakeGoogleAnalyticsClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

            def list_account_summaries(self):
                return [
                    {"kind": "account", "id": "111", "resource_name": "accounts/111", "name": "Agency"},
                    {"kind": "property", "id": "123456", "resource_name": "properties/123456", "name": "Acme Web", "account": "accounts/111"},
                ]

            def run_report(self, *, property_id, metrics, dimensions, start_date, end_date, limit):
                if dimensions == ["eventName"]:
                    return GoogleAnalyticsReport(
                        rows=[
                            {"dimensions": {"eventName": "generate_lead"}, "metrics": {"eventCount": 6, "keyEvents": 6}},
                            {"dimensions": {"eventName": "scroll"}, "metrics": {"eventCount": 40, "keyEvents": 0}},
                        ],
                        row_count=2,
                        metadata={},
                    )
                return GoogleAnalyticsReport(
                    rows=[{"metrics": {"sessions": 120, "activeUsers": 50, "totalUsers": 60, "eventCount": 900, "keyEvents": 9}}],
                    row_count=1,
                    metadata={},
                )

        capsule = ClientCapsule(
            client_id="acme",
            name="Acme",
            systems=default_systems(crm="mock_crm", ads="mock_ads", analytics="google_analytics", client_id="acme"),
            metrics={
                **default_metric_definitions(analytics="google_analytics"),
                "conversion_definitions": {
                    "ga4_lead": {
                        "source": "google_analytics",
                        "source_name": "generate_lead",
                        "canonical_metric": "conversions",
                    }
                },
            },
            field_map=default_field_map(crm="mock_crm", ads="mock_ads", analytics="google_analytics"),
        )
        connector = GoogleAnalyticsConnector(client_factory=FakeGoogleAnalyticsClient)
        os.environ["GOOGLE_ANALYTICS_ACME_PROPERTY_ID"] = "123456"
        try:
            discovered = connector.discover_resources(capsule, live=True)
            result = connector.run_query(
                capsule,
                load_manifest(Path(tempfile.mkdtemp()), "website_performance"),
                {"client_id": "acme", "start_date": "2026-01-01", "end_date": "2026-01-31"},
            )
        finally:
            os.environ.pop("GOOGLE_ANALYTICS_ACME_PROPERTY_ID", None)

        self.assertEqual("ok", discovered.status)
        self.assertTrue(any(resource.get("kind") == "property" for resource in discovered.resources))
        self.assertEqual(6, result.metrics["conversions"])
        self.assertEqual(6, result.metrics["key_events"])
        self.assertEqual(6, result.metrics["event_count"])
        self.assertEqual(0.05, result.metrics["conversion_rate"])
        self.assertEqual(1, result.metadata["conversion_mapping"]["ignored_rows"])

    def test_hubspot_client_uses_2026_03_search_and_pagination(self) -> None:
        calls = []

        def transport(method, url, headers, payload, timeout):
            calls.append({"method": method, "url": url, "headers": headers, "payload": payload, "timeout": timeout})
            if "after" not in payload:
                return {
                    "total": 2,
                    "results": [{"id": "1", "properties": {"createdate": "2026-01-01T00:00:00Z"}}],
                    "paging": {"next": {"after": "next-page"}},
                }
            return {"total": 2, "results": [{"id": "2", "properties": {"createdate": "2026-01-02T00:00:00Z"}}]}

        client = HubSpotClient("token", transport=transport)
        page = client.collect_search("contacts", filters=[], properties=["createdate"], limit=200, max_pages=5)

        self.assertEqual(2, len(page.rows))
        self.assertFalse(page.truncated)
        self.assertEqual(2, page.pages_read)
        self.assertIn("/crm/objects/2026-03/contacts/search", calls[0]["url"])
        self.assertEqual("next-page", calls[1]["payload"]["after"])
        self.assertEqual("Bearer token", calls[0]["headers"]["Authorization"])

    def test_hubspot_connector_aggregates_real_metrics_with_field_map(self) -> None:
        class FakeHubSpotClient:
            api_version = "2026-03"

            def __init__(self, token: str) -> None:
                self.token = token

            def collect_search(self, object_type, *, filters=None, properties=None, limit=200, max_pages=50, sorts=None):
                filter_property = filters[0]["propertyName"] if filters else ""
                if object_type == "contacts":
                    return _fake_hubspot_page(
                        [
                            {"id": "1", "properties": {"hs_object_id": "1", "lifecyclestage": "marketingqualifiedlead"}},
                            {"id": "2", "properties": {"hs_object_id": "2", "lifecyclestage": "salesqualifiedlead"}},
                            {"id": "3", "properties": {"hs_object_id": "3", "lifecyclestage": "subscriber"}},
                        ]
                    )
                if object_type == "deals" and filter_property == "createdate":
                    return _fake_hubspot_page(
                        [
                            {"id": "11", "properties": {"amount": "1000", "dealstage": "appointmentscheduled"}},
                            {"id": "12", "properties": {"amount": "2000", "dealstage": "closedlost"}},
                            {"id": "13", "properties": {"amount": "3000", "dealstage": "closedwon"}},
                        ]
                    )
                if object_type == "deals" and filter_property == "closedate":
                    return _fake_hubspot_page(
                        [
                            {"id": "13", "properties": {"amount": "3000", "dealstage": "closedwon"}},
                            {"id": "14", "properties": {"amount": "900", "dealstage": "appointmentscheduled"}},
                        ]
                    )
                return _fake_hubspot_page([])

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            capsule = ClientCapsule(
                client_id="acme",
                name="Acme",
                systems=default_systems(crm="hubspot", ads="mock_ads", client_id="acme"),
                metrics=default_metric_definitions(),
                field_map=default_field_map(crm="hubspot", ads="mock_ads"),
            )
            manifest = load_manifest(root, "pipeline_health")
            os.environ["HUBSPOT_ACME_ACCESS_TOKEN"] = "token"
            try:
                result = HubSpotConnector(client_factory=FakeHubSpotClient).run_query(
                    capsule,
                    manifest,
                    {"client_id": "acme", "start_date": "2026-01-01", "end_date": "2026-01-31"},
                )
            finally:
                os.environ.pop("HUBSPOT_ACME_ACCESS_TOKEN", None)

        self.assertEqual(3, result.metrics["leads"])
        self.assertEqual(3, result.metrics["opportunities"])
        self.assertEqual(4000.0, result.metrics["pipeline_amount"])
        self.assertEqual(3000.0, result.metrics["closed_won_revenue"])
        self.assertEqual("2026-03", result.metadata["api_version"])
        self.assertEqual("none", result.metadata["row_storage"])

    def test_ga4_engagement_rate_is_weighted_by_sessions(self) -> None:
        class FakeGoogleAnalyticsClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

            def run_report(self, *, property_id, metrics, dimensions, start_date, end_date, limit):
                return GoogleAnalyticsReport(
                    rows=[
                        {"metrics": {"sessions": 10, "activeUsers": 5, "eventCount": 20, "keyEvents": 1, "engagementRate": 0.1}},
                        {"metrics": {"sessions": 90, "activeUsers": 40, "eventCount": 200, "keyEvents": 9, "engagementRate": 0.9}},
                    ],
                    row_count=2,
                    metadata={},
                )

        capsule = ClientCapsule(
            client_id="acme",
            name="Acme",
            systems=default_systems(crm="mock_crm", ads="mock_ads", analytics="google_analytics", client_id="acme"),
            metrics=default_metric_definitions(analytics="google_analytics"),
            field_map=default_field_map(crm="mock_crm", ads="mock_ads", analytics="google_analytics"),
        )
        connector = GoogleAnalyticsConnector(client_factory=FakeGoogleAnalyticsClient)
        os.environ["GOOGLE_ANALYTICS_ACME_PROPERTY_ID"] = "123456"
        try:
            result = connector.run_query(
                capsule,
                load_manifest(Path(tempfile.mkdtemp()), "website_performance"),
                {"client_id": "acme", "start_date": "2026-01-01", "end_date": "2026-01-31"},
            )
        finally:
            os.environ.pop("GOOGLE_ANALYTICS_ACME_PROPERTY_ID", None)

        self.assertEqual(0.82, result.metrics["engagement_rate"])

    def test_atomic_json_write_preserves_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "nested" / "artifact.json"
            write_json(path, {"artifact_schema_version": 1, "value": "ok"})
            self.assertEqual("ok", read_json(path)["value"])
            self.assertFalse(any(path.parent.glob("*.tmp")))

    def test_hubspot_connector_static_and_live_setup_modes(self) -> None:
        class FakeHubSpotClient:
            def __init__(self, token: str) -> None:
                self.token = token

            def collect_search(self, object_type, *, filters=None, properties=None, limit=200, max_pages=50, sorts=None):
                return _fake_hubspot_page([])

        capsule = ClientCapsule(
            client_id="beta",
            name="Beta",
            systems=default_systems(crm="hubspot", ads="mock_ads", client_id="beta"),
            field_map=default_field_map(crm="hubspot", ads="mock_ads"),
        )
        connector = HubSpotConnector(client_factory=FakeHubSpotClient)
        os.environ["HUBSPOT_BETA_ACCESS_TOKEN"] = "token"
        try:
            static = connector.check_setup(capsule)
            live = connector.check_setup(capsule, live=True)
        finally:
            os.environ.pop("HUBSPOT_BETA_ACCESS_TOKEN", None)

        self.assertEqual("configured", static.status)
        self.assertEqual("ok", live.status)
        self.assertIn("Static setup checks", static.warnings[0])

    def test_client_archive_export_delete_and_purge_guardrails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            copy_fixture("kg/schema.sql", root)
            copy_fixture("kg/seed_graph.json", root)
            copy_fixture("db/schema.sql", root)
            run_praxis(root, "reach", "init")
            run_praxis(root, "agency", "client", "create", "acme")
            run_praxis(root, "agency", "client", "create", "beta")

            acme_query = run_praxis(root, "reach", "query", "run", "pipeline_health", "--client", "acme")
            beta_query = run_praxis(root, "reach", "query", "run", "pipeline_health", "--client", "beta")
            acme_evidence_id = evidence_id_from(acme_query.stdout)
            beta_evidence_id = evidence_id_from(beta_query.stdout)
            run_praxis(root, "reach", "context", "build", "pipeline_health_check", "--client", "acme")
            run_praxis(root, "reach", "evidence", "capture", acme_evidence_id)

            archive = run_praxis(root, "agency", "client", "archive", "acme", "--reason", "contract ended")
            self.assertIn("status: archived", archive.stdout)
            listed = run_praxis(root, "agency", "client", "list")
            self.assertNotIn("acme: acme", listed.stdout)
            listed_archived = run_praxis(root, "agency", "client", "list", "--include-archived")
            self.assertIn("acme: acme", listed_archived.stdout)
            self.assertIn("status: archived", listed_archived.stdout)

            archived_run = run_praxis(root, "agency", "run", "pipeline_health", "--clients", "acme", check=False)
            self.assertEqual(2, archived_run.returncode)
            self.assertIn("archived and cannot run", archived_run.stdout)

            exported = run_praxis(root, "agency", "client", "export", "acme")
            export_path = Path(exported.stdout.split("export:", 1)[1].splitlines()[0].strip())
            self.assertTrue(export_path.exists())
            with tarfile.open(export_path, "r:gz") as archive_file:
                names = archive_file.getnames()
            self.assertIn("acme/export_manifest.json", names)
            self.assertTrue(any(name.endswith("agency/clients/acme/client.json") for name in names))

            plan_output = run_praxis(root, "agency", "client", "delete-plan", "acme", "--reason", "privacy request")
            plan_id = _match_value(plan_output.stdout, "plan_id")
            self.assertIn("confirmation_required", plan_output.stdout)
            self.assertIn("agency/clients/acme", plan_output.stdout)
            self.assertIn("reach/evidence", plan_output.stdout)

            bad_delete = run_praxis(
                root,
                "agency",
                "client",
                "delete",
                "--plan",
                plan_id,
                "--confirm-client",
                "beta",
                "--confirm-delete",
                "DELETE",
                check=False,
            )
            self.assertEqual(2, bad_delete.returncode)
            self.assertIn("--confirm-client must exactly match acme", bad_delete.stdout)

            deleted = run_praxis(
                root,
                "agency",
                "client",
                "delete",
                "--plan",
                plan_id,
                "--confirm-client",
                "acme",
                "--confirm-delete",
                "DELETE",
            )
            receipt_id = _match_value(deleted.stdout, "receipt_id")
            quarantine_path = Path(deleted.stdout.split("quarantine_path:", 1)[1].splitlines()[0].strip())
            self.assertFalse((root / "agency" / "clients" / "acme").exists())
            self.assertTrue((root / "agency" / "clients" / "beta").exists())
            self.assertTrue((root / quarantine_path).exists())

            evidence_list = run_praxis(root, "reach", "evidence", "list", check=False)
            self.assertIn(beta_evidence_id, evidence_list.stdout)
            self.assertNotIn(acme_evidence_id, evidence_list.stdout)

            bad_purge = run_praxis(
                root,
                "agency",
                "client",
                "purge",
                "--receipt",
                receipt_id,
                "--confirm-delete",
                "DELETE",
                check=False,
            )
            self.assertEqual(2, bad_purge.returncode)
            self.assertIn('"PURGE"', bad_purge.stdout)

            purged = run_praxis(
                root,
                "agency",
                "client",
                "purge",
                "--receipt",
                receipt_id,
                "--confirm-delete",
                "PURGE",
            )
            self.assertIn("status: purged", purged.stdout)
            self.assertFalse((root / quarantine_path).exists())

    def test_delete_requires_archive_or_explicit_no_archive_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_praxis(root, "reach", "init")
            run_praxis(root, "agency", "client", "create", "acme")
            plan_output = run_praxis(root, "agency", "client", "delete-plan", "acme")
            plan_id = _match_value(plan_output.stdout, "plan_id")

            refused = run_praxis(
                root,
                "agency",
                "client",
                "delete",
                "--plan",
                plan_id,
                "--confirm-client",
                "acme",
                "--confirm-delete",
                "DELETE",
                check=False,
            )
            self.assertEqual(2, refused.returncode)
            self.assertIn("requires an archive/export first", refused.stdout)

            missing_reason = run_praxis(
                root,
                "agency",
                "client",
                "delete",
                "--plan",
                plan_id,
                "--confirm-client",
                "acme",
                "--confirm-delete",
                "DELETE",
                "--no-archive",
                check=False,
            )
            self.assertEqual(2, missing_reason.returncode)
            self.assertIn("--no-archive requires --reason", missing_reason.stdout)


def _fake_hubspot_page(rows):
    from praxis.reach.connectors.hubspot_client import HubSpotPage

    return HubSpotPage(rows=list(rows), total=len(rows), pages_read=1)


def _match_value(output: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", output, flags=re.MULTILINE)
    if not match:
        raise AssertionError(f"No {key} found in output:\n{output}")
    return match.group(1).strip()


if __name__ == "__main__":
    unittest.main()
