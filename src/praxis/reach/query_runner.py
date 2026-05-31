"""Run Reach query manifests through read-only connectors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .connectors import available_connectors
from .connectors.base import ConnectorResult
from .evidence import EvidenceCard, create_evidence_card
from .manifests import QueryManifest
from .models import ClientCapsule


def providers_for_requirement(capsule: ClientCapsule, requirement: str) -> list[str]:
    value = capsule.systems.get(requirement)
    providers: list[str] = []
    if isinstance(value, dict) and value.get("provider"):
        providers.append(str(value["provider"]))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("provider"):
                providers.append(str(item["provider"]))
    return providers


def validate_connector_contract(provider: str, capabilities: dict[str, Any], manifest: QueryManifest) -> list[str]:
    errors: list[str] = []
    if capabilities.get("mode") != "read_only":
        errors.append(f"{provider}: connector must declare mode=read_only")
    supported_storage = set(capabilities.get("storage_levels") or [])
    if supported_storage and manifest.storage_level not in supported_storage:
        errors.append(f"{provider}: connector does not support storage level {manifest.storage_level}")
    return errors


def validate_connector_result(
    provider: str,
    result: ConnectorResult,
    manifest: QueryManifest,
    allowed_storage_levels: set[str],
) -> list[str]:
    errors: list[str] = []
    if result.provider != provider:
        errors.append(f"{provider}: connector returned provider {result.provider}")
    if result.storage_level not in allowed_storage_levels:
        errors.append(f"{provider}: result storage level {result.storage_level} is not allowed")
    unexpected = sorted(set(result.metrics) - set(manifest.outputs))
    if unexpected:
        errors.append(f"{provider}: result included metrics outside manifest outputs: {', '.join(unexpected)}")
    return errors


def run_manifest(root: Path, capsule: ClientCapsule, manifest: QueryManifest, params: dict[str, Any]) -> EvidenceCard:
    manifest_errors = manifest.validate()
    if manifest_errors:
        raise RuntimeError("Invalid query manifest: " + "; ".join(manifest_errors))
    param_errors = manifest.validate_params(params)
    if param_errors:
        raise RuntimeError("Invalid query parameters: " + "; ".join(param_errors))
    allowed = set(capsule.permissions.get("allowed_storage_levels", []))
    if not allowed:
        raise RuntimeError(f"Client {capsule.client_id} does not allow any Reach storage levels")
    if allowed and manifest.storage_level not in allowed:
        raise RuntimeError(f"Storage level {manifest.storage_level} is not allowed for client {capsule.client_id}")
    registry = available_connectors()
    results = []
    missing: list[str] = []
    connector_params = {**params, "root": str(root)}
    for requirement in manifest.requires:
        for provider in providers_for_requirement(capsule, requirement):
            connector_type = registry.get(provider)
            if connector_type is None:
                missing.append(provider)
                continue
            connector = connector_type()
            contract_errors = validate_connector_contract(provider, connector.capabilities(), manifest)
            if contract_errors:
                raise RuntimeError("; ".join(contract_errors))
            result = connector.run_query(capsule, manifest, connector_params)
            result_errors = validate_connector_result(provider, result, manifest, allowed)
            if result_errors:
                raise RuntimeError("; ".join(result_errors))
            results.append(result)
    if missing:
        raise RuntimeError(
            "No installed Reach connector for: "
            + ", ".join(sorted(set(missing)))
            + ". Check `praxis reach connectors list` and install/configure the required connector."
        )
    if not results:
        raise RuntimeError(f"No connectors matched query requirements: {', '.join(manifest.requires)}")
    return create_evidence_card(root, capsule, manifest, params, results)
