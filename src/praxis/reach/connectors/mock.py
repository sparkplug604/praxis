"""Deterministic demo connectors for Praxis Reach tests and examples."""

from __future__ import annotations

from typing import Any

from .base import ConnectorCheck, ConnectorResult
from praxis.reach.manifests import QueryManifest
from praxis.reach.models import ClientCapsule


class MockCRMConnector:
    provider = "mock_crm"
    connector_version = "mock-crm-v1"

    def capabilities(self) -> dict[str, Any]:
        return {
            "kind": "crm",
            "mode": "read_only",
            "objects": ["contact", "company", "opportunity"],
            "metrics": ["leads", "opportunities", "pipeline_amount", "closed_won_revenue"],
            "supports_deep_links": True,
            "storage_levels": ["metadata", "aggregate_summary"],
        }

    def list_resources(self, capsule: ClientCapsule) -> list[str]:
        return ["contacts", "companies", "opportunities", "pipeline"]

    def introspect_schema(self, capsule: ClientCapsule) -> dict[str, Any]:
        return {
            "contacts": ["id", "created_at", "lifecycle_stage", "source"],
            "opportunities": ["id", "amount", "stage", "close_date", "source"],
        }

    def check_setup(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorCheck:
        return ConnectorCheck(provider=self.provider, status="ok", message="Mock CRM connector is ready.")

    def run_query(self, capsule: ClientCapsule, manifest: QueryManifest, params: dict[str, Any]) -> ConnectorResult:
        client_seed = max(len(capsule.client_id), 1)
        leads = 40 + client_seed
        opportunities = 9 + client_seed
        pipeline = 50000 + (client_seed * 2500)
        metrics = {
            "leads": leads,
            "opportunities": opportunities,
            "pipeline_amount": pipeline,
            "closed_won_revenue": round(pipeline * 0.28, 2),
        }
        return ConnectorResult(
            provider=self.provider,
            summary=f"Mock CRM found {leads} leads, {opportunities} opportunities, and {pipeline} pipeline value.",
            metrics={key: value for key, value in metrics.items() if key in manifest.outputs},
            source_links=[f"mock://{capsule.client_id}/crm/{manifest.manifest_id}"],
            row_count=leads + opportunities,
            metadata={"mode": "demo", "params": params, "connector_version": self.connector_version},
        )


class MockAdsConnector:
    provider = "mock_ads"
    connector_version = "mock-ads-v1"

    def capabilities(self) -> dict[str, Any]:
        return {
            "kind": "ads",
            "mode": "read_only",
            "objects": ["campaign", "ad_group", "ad", "metric_snapshot"],
            "metrics": ["spend", "reach", "impressions", "clicks", "ctr", "cpc", "cpm"],
            "supports_deep_links": True,
            "storage_levels": ["metadata", "aggregate_summary"],
        }

    def list_resources(self, capsule: ClientCapsule) -> list[str]:
        return ["campaigns", "ad_groups", "ads", "metric_snapshots"]

    def introspect_schema(self, capsule: ClientCapsule) -> dict[str, Any]:
        return {
            "campaigns": ["id", "name", "channel", "status"],
            "metric_snapshots": ["date", "spend", "reach", "impressions", "clicks"],
        }

    def check_setup(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorCheck:
        return ConnectorCheck(provider=self.provider, status="ok", message="Mock ads connector is ready.")

    def run_query(self, capsule: ClientCapsule, manifest: QueryManifest, params: dict[str, Any]) -> ConnectorResult:
        client_seed = max(len(capsule.client_id), 1)
        spend = 12000 + (client_seed * 900)
        reach = 85000 - (client_seed * 250)
        impressions = reach * 2
        clicks = 3400 + (client_seed * 55)
        metrics = {
            "spend": spend,
            "reach": reach,
            "impressions": impressions,
            "clicks": clicks,
        }
        if "leads" in manifest.outputs:
            metrics["leads"] = 55 + client_seed
        warnings = []
        if "leads" in manifest.outputs:
            warnings.append("Ad-platform lead counts are directional until confirmed by CRM.")
        return ConnectorResult(
            provider=self.provider,
            summary=f"Mock ads reported {reach} reach, {impressions} impressions, and {spend} spend.",
            metrics={key: value for key, value in metrics.items() if key in manifest.outputs},
            source_links=[f"mock://{capsule.client_id}/ads/{manifest.manifest_id}"],
            warnings=warnings,
            row_count=90,
            metadata={"mode": "demo", "params": params, "connector_version": self.connector_version},
        )
