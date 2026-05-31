"""CLI formatting helpers for Praxis Agency commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from praxis.agency.lifecycle import is_archived
from praxis.agency.runner import AgencyRunOutcome
from praxis.reach.models import ClientCapsule


def print_client_list(root: Path, clients: list[ClientCapsule]) -> None:
    print("# Agency clients\n")
    if not clients:
        print("No client capsules found.")
        return
    for capsule in clients:
        status = "archived" if is_archived(root, capsule.client_id) else "active"
        print(f"- {capsule.client_id}: {capsule.name}")
        print(f"  status: {status}")
        print(f"  providers: {', '.join(capsule.providers()) or 'none'}")


def print_client_summary(root: Path, capsule: ClientCapsule) -> None:
    print(f"# {capsule.name}\n")
    print(f"- client_id: {capsule.client_id}")
    print(f"- status: {'archived' if is_archived(root, capsule.client_id) else 'active'}")
    print(f"- timezone: {capsule.timezone}")
    print(f"- currency: {capsule.currency}")
    print(f"- providers: {', '.join(capsule.providers()) or 'none'}")
    print("\n## Permissions\n")
    for key, value in sorted(capsule.permissions.items()):
        print(f"- {key}: {value}")
    print("\n## Metrics\n")
    metric_map = capsule.metrics.get("metrics", capsule.metrics)
    for key, value in sorted(metric_map.items()):
        description = value.get("description") if isinstance(value, dict) else value
        print(f"- {key}: {description}")


def print_field_map(capsule: ClientCapsule) -> None:
    print(f"# Field map: {capsule.client_id}\n")
    for object_id, mapping in sorted(capsule.field_map.get("objects", {}).items()):
        print(f"## {object_id}")
        print(f"- source: {mapping.get('source', '')}")
        for field, source_field in sorted(dict(mapping.get("fields") or {}).items()):
            print(f"- {field}: {source_field}")
        print()


def print_metric_definitions(capsule: ClientCapsule) -> None:
    print(f"# Metrics: {capsule.client_id}\n")
    for metric_id, definition in sorted(capsule.metrics.get("metrics", capsule.metrics).items()):
        if not isinstance(definition, dict):
            print(f"- {metric_id}: {definition}")
            continue
        print(f"- {metric_id}")
        print(f"  canonical_object: {definition.get('canonical_object', '')}")
        print(f"  description: {definition.get('description', '')}")
        if definition.get("definition"):
            print(f"  definition: {definition['definition']}")
        if definition.get("source_priority"):
            print(f"  source_priority: {', '.join(definition['source_priority'])}")
    conversion_definitions = capsule.metrics.get("conversion_definitions") or {}
    if conversion_definitions:
        print("\n## Conversion Definitions\n")
        for conversion_id, definition in sorted(conversion_definitions.items()):
            if not isinstance(definition, dict):
                print(f"- {conversion_id}: {definition}")
                continue
            print(f"- {conversion_id}")
            print(f"  source: {definition.get('source', '')}")
            print(f"  source_name: {definition.get('source_name', '')}")
            print(f"  source_id: {definition.get('source_id', '')}")
            print(f"  canonical_metric: {definition.get('canonical_metric', '')}")
            print(f"  weight: {definition.get('weight', '')}")
            print(f"  primary: {definition.get('primary', '')}")


def print_delete_plan(plan: dict[str, Any]) -> None:
    print(f"plan_id: {plan['plan_id']}")
    print(f"client_id: {plan['client_id']}")
    print(f"status: {plan['status']}")
    print(f"archive_required: {plan['archive_required']}")
    print(f"archive_present: {plan['archive_present']}")
    print(f"target_count: {len(plan.get('targets', []))}")
    if plan.get("warnings"):
        print("warnings:")
        for warning in plan["warnings"]:
            print(f"- {warning}")
    if plan.get("targets"):
        print("targets:")
        for target in plan["targets"]:
            print(f"- {target['kind']}: {target['path']} ({target['reason']})")
    database_records = plan.get("database_records") or {}
    if database_records.get("source_ids"):
        print("database_records:")
        print(f"- source_ids: {len(database_records['source_ids'])}")
        for database, counts in database_records.items():
            if isinstance(counts, dict) and counts:
                print(f"- {database}: {counts}")


def print_agency_run(results: list[AgencyRunOutcome]) -> bool:
    print("# Agency run\n")
    had_errors = False
    for outcome in results:
        print(f"- client_id: {outcome.client_id}")
        if outcome.error:
            had_errors = True
            print("  status: error")
            print(f"  error: {outcome.error}")
            continue
        if outcome.card is None:
            had_errors = True
            print("  status: error")
            print("  error: no evidence card produced")
            continue
        print("  status: ok")
        print(f"  evidence_id: {outcome.card.evidence_id}")
        print(f"  query_id: {outcome.card.query_id}")
        print(f"  warnings: {len(outcome.card.warnings)}")
        if outcome.context_path:
            print(f"  context_pack: {outcome.context_path}")
    return had_errors
