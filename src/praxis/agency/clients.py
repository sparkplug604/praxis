"""Client capsule management for agencies using Praxis Reach."""

from __future__ import annotations

from pathlib import Path

from praxis.agency.client_validation import validate_client
from praxis.agency.lifecycle import is_archived
from praxis.reach.models import ClientCapsule, default_systems
from praxis.reach.ontology import default_field_map, default_metric_definitions, validate_field_map, validate_metric_definitions
from praxis.reach.storage import (
    client_capsule_path,
    client_dir,
    client_field_map_path,
    client_metrics_path,
    client_permissions_path,
    client_systems_path,
    agency_dir,
    read_json,
    slug,
    write_json,
)


CLIENT_ARTIFACT_SCHEMA_VERSION = 1


def create_client(
    root: Path,
    client_id: str,
    *,
    name: str | None = None,
    timezone: str = "UTC",
    currency: str = "USD",
    crm: str = "mock_crm",
    ads: str = "mock_ads",
    analytics: str | None = None,
    warehouse: str | None = None,
    overwrite: bool = False,
) -> ClientCapsule:
    normalized_client_id = slug(client_id)
    capsule = ClientCapsule(
        client_id=normalized_client_id,
        name=name or client_id,
        timezone=timezone,
        currency=currency,
        systems=default_systems(crm=crm, ads=ads, analytics=analytics, warehouse=warehouse, client_id=normalized_client_id),
        metrics=default_metric_definitions(analytics=analytics),
        field_map=default_field_map(crm=crm, ads=ads, analytics=analytics),
        permissions={},
    )
    path = client_capsule_path(root, capsule.client_id)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Client already exists: {capsule.client_id}. Use --overwrite to replace it.")
    write_client(root, capsule)
    return capsule


def write_client(root: Path, capsule: ClientCapsule) -> None:
    capsule_dir = client_dir(root, capsule.client_id)
    capsule_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        client_capsule_path(root, capsule.client_id),
        {
            "artifact_schema_version": CLIENT_ARTIFACT_SCHEMA_VERSION,
            "client": {
                "id": capsule.client_id,
                "name": capsule.name,
                "timezone": capsule.timezone,
                "currency": capsule.currency,
            }
        },
    )
    write_json(client_systems_path(root, capsule.client_id), {"artifact_schema_version": CLIENT_ARTIFACT_SCHEMA_VERSION, "systems": capsule.systems})
    field_map = dict(capsule.field_map or default_field_map())
    field_map.setdefault("artifact_schema_version", CLIENT_ARTIFACT_SCHEMA_VERSION)
    write_json(client_field_map_path(root, capsule.client_id), field_map)
    metrics = dict(capsule.metrics or default_metric_definitions())
    metrics.setdefault("artifact_schema_version", CLIENT_ARTIFACT_SCHEMA_VERSION)
    write_json(client_metrics_path(root, capsule.client_id), metrics)
    write_json(
        client_permissions_path(root, capsule.client_id),
        {"artifact_schema_version": CLIENT_ARTIFACT_SCHEMA_VERSION, "permissions": capsule.permissions or capsule.policies},
    )


def load_client(root: Path, client_id: str) -> ClientCapsule:
    path = client_capsule_path(root, client_id)
    if not path.exists():
        raise KeyError(f"Unknown client capsule: {client_id}")
    data = read_json(path)
    data.update(read_json(client_systems_path(root, client_id)) if client_systems_path(root, client_id).exists() else {})
    if client_metrics_path(root, client_id).exists():
        data["metrics"] = read_json(client_metrics_path(root, client_id))
    if client_field_map_path(root, client_id).exists():
        data["field_map"] = read_json(client_field_map_path(root, client_id))
    if client_permissions_path(root, client_id).exists():
        data.update(read_json(client_permissions_path(root, client_id)))
    return ClientCapsule.from_dict(data)


def list_clients(root: Path, *, include_archived: bool = False) -> list[ClientCapsule]:
    base = agency_dir(root) / "clients"
    if not base.exists():
        return []
    clients: list[ClientCapsule] = []
    for path in sorted(base.glob("*/client.json")):
        capsule = load_client(root, path.parent.name)
        if not include_archived and is_archived(root, capsule.client_id):
            continue
        clients.append(capsule)
    return clients


def client_exists(root: Path, client_id: str) -> bool:
    return client_capsule_path(root, client_id).exists()


def client_workspace(root: Path, client_id: str) -> Path:
    return client_dir(root, client_id)


def set_field_mapping(
    root: Path,
    client_id: str,
    *,
    object_id: str,
    source: str | None = None,
    field: str | None = None,
    source_field: str | None = None,
) -> dict:
    capsule = load_client(root, client_id)
    field_map = dict(capsule.field_map or default_field_map())
    objects = dict(field_map.setdefault("objects", {}))
    mapping = dict(objects.get(object_id) or {"fields": {}})
    if source:
        mapping["source"] = source
    fields = dict(mapping.get("fields") or {})
    if field and source_field:
        fields[field] = source_field
    mapping["fields"] = fields
    objects[object_id] = mapping
    field_map["objects"] = objects
    errors = validate_field_map(field_map)
    if errors:
        raise RuntimeError("; ".join(errors))
    write_json(client_field_map_path(root, client_id), field_map)
    return field_map


def set_metric_definition(
    root: Path,
    client_id: str,
    metric_id: str,
    *,
    canonical_object: str,
    description: str,
    source_priority: list[str],
    definition: str,
) -> dict:
    capsule = load_client(root, client_id)
    metrics = dict(capsule.metrics or default_metric_definitions())
    metric_map = dict(metrics.setdefault("metrics", {}))
    metric_map[metric_id] = {
        "canonical_object": canonical_object,
        "description": description,
        "source_priority": source_priority,
        "definition": definition,
    }
    metrics["metrics"] = metric_map
    errors = validate_metric_definitions(metrics)
    if errors:
        raise RuntimeError("; ".join(errors))
    write_json(client_metrics_path(root, client_id), metrics)
    return metrics


def set_conversion_definition(
    root: Path,
    client_id: str,
    conversion_id: str,
    *,
    source: str,
    source_name: str = "",
    source_id: str = "",
    canonical_metric: str = "conversions",
    weight: float = 1.0,
    primary: bool = True,
    description: str = "",
) -> dict:
    if not source_name and not source_id:
        raise RuntimeError("conversion definitions require --source-name or --source-id")
    metrics = dict(load_client(root, client_id).metrics or default_metric_definitions())
    definitions = metrics.get("conversion_definitions", {})
    if isinstance(definitions, list):
        definitions = {
            str(item.get("id") or item.get("name") or index): item
            for index, item in enumerate(definitions)
            if isinstance(item, dict)
        }
    if not isinstance(definitions, dict):
        definitions = {}
    definitions[conversion_id] = {
        "id": conversion_id,
        "source": source,
        "source_name": source_name,
        "source_id": source_id,
        "canonical_metric": canonical_metric,
        "weight": weight,
        "primary": primary,
        "description": description,
    }
    metrics["conversion_definitions"] = definitions
    errors = validate_metric_definitions(metrics)
    if errors:
        raise RuntimeError("; ".join(errors))
    write_json(client_metrics_path(root, client_id), metrics)
    return metrics
