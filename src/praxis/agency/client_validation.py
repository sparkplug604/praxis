"""Validation rules for Praxis Agency client capsules."""

from __future__ import annotations

from praxis.reach.connectors import available_connectors
from praxis.reach.models import ClientCapsule
from praxis.reach.ontology import validate_field_map, validate_metric_definitions


def validate_client(capsule: ClientCapsule) -> list[str]:
    errors: list[str] = []
    errors.extend(_validate_identity_and_permissions(capsule))
    errors.extend(_validate_configured_providers(capsule))
    errors.extend(_validate_storage_permissions(capsule))
    errors.extend(_validate_field_sources(capsule))
    errors.extend(_validate_metric_sources(capsule))
    errors.extend(validate_field_map(capsule.field_map))
    errors.extend(validate_metric_definitions(capsule.metrics))
    return errors


def _validate_identity_and_permissions(capsule: ClientCapsule) -> list[str]:
    errors: list[str] = []
    if not capsule.client_id:
        errors.append("client.id is required")
    if not capsule.systems:
        errors.append("systems.json must define at least one system")
    if capsule.permissions.get("mode") != "read_only":
        errors.append("permissions.mode must be read_only")
    if capsule.permissions.get("pii_storage") != "none":
        errors.append("permissions.pii_storage must be none")
    if capsule.permissions.get("writeback") != "disabled":
        errors.append("permissions.writeback must be disabled")
    if not capsule.providers():
        errors.append("at least one provider is required")
    return errors


def _validate_configured_providers(capsule: ClientCapsule) -> list[str]:
    errors: list[str] = []
    registry = available_connectors()
    for system_kind, provider in _configured_providers(capsule):
        connector_type = registry.get(provider)
        if connector_type is None:
            errors.append(f"{provider}: no installed connector")
            continue
        capabilities = connector_type().capabilities()
        provider_kind = str(capabilities.get("kind") or "")
        if capabilities.get("mode") != "read_only":
            errors.append(f"{provider}: connector must be read_only")
        if provider_kind and provider_kind != system_kind:
            errors.append(f"{provider}: connector kind {provider_kind} does not match system {system_kind}")
    return errors


def _validate_storage_permissions(capsule: ClientCapsule) -> list[str]:
    allowed_storage = capsule.permissions.get("allowed_storage_levels")
    if not isinstance(allowed_storage, list) or not allowed_storage:
        return ["permissions.allowed_storage_levels must list permitted storage levels"]
    invalid = sorted(set(str(item) for item in allowed_storage) - {"pointer", "metadata", "aggregate_summary", "redacted_sample"})
    return [f"permissions.allowed_storage_levels has unsupported values: {', '.join(invalid)}"] if invalid else []


def _validate_field_sources(capsule: ClientCapsule) -> list[str]:
    errors: list[str] = []
    objects = capsule.field_map.get("objects", {})
    if not isinstance(objects, dict):
        return errors
    providers = set(capsule.providers())
    for object_id, mapping in objects.items():
        if not isinstance(mapping, dict):
            continue
        source = str(mapping.get("source") or "")
        source_provider = source.split(".", 1)[0] if "." in source else source
        if source_provider and source_provider not in providers:
            errors.append(f"{object_id}.source references unconfigured provider: {source_provider}")
    return errors


def _validate_metric_sources(capsule: ClientCapsule) -> list[str]:
    errors: list[str] = []
    metric_map = capsule.metrics.get("metrics", capsule.metrics)
    if not isinstance(metric_map, dict):
        return errors
    allowed_sources = set(capsule.systems) | set(capsule.providers())
    for metric_id, definition in metric_map.items():
        if not isinstance(definition, dict):
            continue
        for source in definition.get("source_priority") or []:
            if str(source) not in allowed_sources:
                errors.append(f"{metric_id}.source_priority references unconfigured source: {source}")
    return errors


def _configured_providers(capsule: ClientCapsule) -> list[tuple[str, str]]:
    providers: list[tuple[str, str]] = []
    for system_kind, value in capsule.systems.items():
        if isinstance(value, dict) and value.get("provider"):
            providers.append((str(system_kind), str(value["provider"])))
        elif isinstance(value, list):
            providers.extend(
                (str(system_kind), str(item["provider"]))
                for item in value
                if isinstance(item, dict) and item.get("provider")
            )
    return providers
