"""Local JSON fixture connectors for Reach demos and tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import ConnectorCheck, ConnectorResult
from .mock import MockAdsConnector, MockCRMConnector
from praxis.reach.manifests import QueryManifest
from praxis.reach.models import ClientCapsule
from praxis.reach.storage import fixtures_dir


def fixture_path(params: dict[str, Any], client_id: str, provider: str) -> Path | None:
    root = params.get("root")
    if not root:
        return None
    path = fixtures_dir(Path(str(root))) / client_id / f"{provider}.json"
    return path if path.exists() else None


class FixtureCRMConnector(MockCRMConnector):
    provider = "fixture_crm"
    connector_version = "fixture-crm-v1"

    def capabilities(self) -> dict[str, Any]:
        data = super().capabilities()
        data["data_mode"] = "fixture"
        return data

    def check_setup(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorCheck:
        path = fixture_path({"root": "."}, capsule.client_id, self.provider)
        return ConnectorCheck(
            provider=self.provider,
            status="ok",
            message="Fixture CRM connector is ready; missing fixture files fall back to deterministic demo data.",
            details={"fixture_file": str(path) if path else ""},
        )

    def run_query(self, capsule: ClientCapsule, manifest: QueryManifest, params: dict[str, Any]) -> ConnectorResult:
        path = fixture_path(params, capsule.client_id, self.provider)
        if path is None:
            result = super().run_query(capsule, manifest, params)
            return ConnectorResult(
                provider=self.provider,
                summary=f"Fixture CRM fallback: {result.summary}",
                metrics=result.metrics,
                source_links=[f"fixture://{capsule.client_id}/crm/{manifest.manifest_id}"],
                warnings=result.warnings + ["No fixture_crm.json found; used deterministic fallback data."],
                row_count=result.row_count,
                metadata={**result.metadata, "connector_version": self.connector_version},
            )
        data = _read_fixture(path)
        return _result_from_fixture(self.provider, self.connector_version, manifest, data)


class FixtureAdsConnector(MockAdsConnector):
    provider = "fixture_ads"
    connector_version = "fixture-ads-v1"

    def capabilities(self) -> dict[str, Any]:
        data = super().capabilities()
        data["data_mode"] = "fixture"
        return data

    def check_setup(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorCheck:
        path = fixture_path({"root": "."}, capsule.client_id, self.provider)
        return ConnectorCheck(
            provider=self.provider,
            status="ok",
            message="Fixture ads connector is ready; missing fixture files fall back to deterministic demo data.",
            details={"fixture_file": str(path) if path else ""},
        )

    def run_query(self, capsule: ClientCapsule, manifest: QueryManifest, params: dict[str, Any]) -> ConnectorResult:
        path = fixture_path(params, capsule.client_id, self.provider)
        if path is None:
            result = super().run_query(capsule, manifest, params)
            return ConnectorResult(
                provider=self.provider,
                summary=f"Fixture ads fallback: {result.summary}",
                metrics=result.metrics,
                source_links=[f"fixture://{capsule.client_id}/ads/{manifest.manifest_id}"],
                warnings=result.warnings + ["No fixture_ads.json found; used deterministic fallback data."],
                row_count=result.row_count,
                metadata={**result.metadata, "connector_version": self.connector_version},
            )
        data = _read_fixture(path)
        return _result_from_fixture(self.provider, self.connector_version, manifest, data)


def _read_fixture(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _result_from_fixture(provider: str, connector_version: str, manifest: QueryManifest, data: dict[str, Any]) -> ConnectorResult:
    metrics = {
        key: value
        for key, value in dict(data.get("metrics") or {}).items()
        if key in manifest.outputs
    }
    return ConnectorResult(
        provider=provider,
        summary=str(data.get("summary") or f"Loaded fixture data for {provider}."),
        metrics=metrics,
        source_links=[str(item) for item in data.get("source_links", [f"fixture://{provider}/{manifest.manifest_id}"])],
        warnings=[str(item) for item in data.get("warnings", [])],
        row_count=int(data.get("row_count") or 0),
        storage_level=str(data.get("storage_level") or manifest.storage_level),
        metadata={
            "mode": "fixture",
            "connector_version": connector_version,
            "conflicts": [str(item) for item in data.get("conflicts", [])],
        },
    )
