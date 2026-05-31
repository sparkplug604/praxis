"""CLI formatting helpers for Praxis Reach commands."""

from __future__ import annotations

from typing import Any

from praxis.reach.connectors.base import ConnectorCheck, ConnectorDiscovery
from praxis.reach.evidence import EvidenceCard
from praxis.reach.freshness import evidence_age_hours
from praxis.reach.manifests import QueryManifest


def print_manifest_summary(manifest: QueryManifest) -> None:
    print(f"- {manifest.manifest_id}: {manifest.description}")
    print(f"  requires: {', '.join(manifest.requires) or 'none'}")
    print(f"  outputs: {', '.join(manifest.outputs) or 'none'}")


def print_connector_check(check: ConnectorCheck, *, client_id: str) -> None:
    print(f"provider: {check.provider}")
    print(f"client_id: {client_id}")
    print(f"status: {check.status}")
    if check.message:
        print(f"message: {check.message}")
    print_mapping_section("details", check.details)
    print_list_section("warnings", check.warnings)


def print_connector_discovery(result: ConnectorDiscovery, *, client_id: str) -> None:
    print(f"provider: {result.provider}")
    print(f"client_id: {client_id}")
    print(f"status: {result.status}")
    if result.message:
        print(f"message: {result.message}")
    print_mapping_section("details", result.details)
    if result.resources:
        print("resources:")
        for resource in result.resources:
            label = resource.get("name") or resource.get("resource_name") or resource.get("id") or "resource"
            print(f"- {label}")
            for key, value in sorted(resource.items()):
                if key == "name":
                    continue
                print(f"  {key}: {value}")
    print_list_section("warnings", result.warnings)


def print_query_result(card: EvidenceCard) -> None:
    print(f"evidence_id: {card.evidence_id}")
    print(f"client_id: {card.client_id}")
    print(f"query_id: {card.query_id}")
    print(f"fresh_at: {card.fresh_at}")
    print(f"data_quality_status: {card.data_quality_status}")
    print(f"confidence_score: {card.confidence_score:.2f}")
    print(f"partial_data: {card.partial_data}")
    print(f"storage_level: {card.storage_level}")
    print(f"row_count: {card.row_count}")
    print_list_section("warnings", card.warnings)
    print_list_section("conflicts", card.conflicts)


def print_evidence_list(cards: list[EvidenceCard]) -> None:
    print("# Reach evidence cards\n")
    if not cards:
        print("No evidence cards found.")
        return
    for card in cards:
        print(f"- {card.evidence_id}")
        print(f"  client_id: {card.client_id}")
        print(f"  query_id: {card.query_id}")
        print(f"  fresh_at: {card.fresh_at}")


def print_evidence_detail(card: EvidenceCard) -> None:
    print(f"# {card.evidence_id}\n")
    print(f"- client_id: {card.client_id}")
    print(f"- query_id: {card.query_id}")
    print(f"- fresh_at: {card.fresh_at}")
    print(f"- sources: {', '.join(card.sources)}")
    print(f"- row_count: {card.row_count}")
    print(f"- storage_level: {card.storage_level}")
    print(f"- manifest_version: {card.manifest_version}")
    print(f"- freshness_status: {card.freshness_status}")
    print(f"- data_quality_status: {card.data_quality_status}")
    print(f"- confidence_score: {card.confidence_score:.2f}")
    print(f"- partial_data: {card.partial_data}")
    print(f"- redaction_status: {card.redaction_status}")
    if card.connector_versions:
        print(f"- connector_versions: {card.connector_versions}")
    if card.source_metadata:
        print(f"- source_metadata: {card.source_metadata}")
    print("\n## Summary\n")
    print(card.summary)
    print("\n## Metrics\n")
    for key, value in sorted(card.metrics.items()):
        source = card.metric_sources.get(key)
        suffix = f" (source: {source})" if source else ""
        print(f"- {key}: {value}{suffix}")
    if card.metric_lineage:
        print("\n## Metric Lineage\n")
        for key, lineage in sorted(card.metric_lineage.items()):
            print(f"- {key}: selected {lineage.get('selected_provider')} via {lineage.get('selection_rule')}")
            for candidate in lineage.get("candidates", []):
                print(f"  candidate: {candidate.get('provider')}={candidate.get('value')} rank={candidate.get('rank')}")
    print_list_section("Warnings", card.warnings, heading_level=2)
    print_list_section("Conflicts", card.conflicts, heading_level=2)
    if card.conflict_records:
        print("\n## Conflict Records\n")
        for conflict in card.conflict_records:
            print(f"- {conflict.get('conflict_id')}: {conflict.get('severity')} / {conflict.get('status')}")
            print(f"  type: {conflict.get('conflict_type')}")
            print(f"  metric: {conflict.get('metric')}")
            print(f"  message: {conflict.get('message')}")
    print("\n## Source Links\n")
    for link in card.source_links:
        print(f"- {link}")


def print_stale_evidence(stale: list[tuple[EvidenceCard, QueryManifest, str]]) -> None:
    print("# Reach stale evidence\n")
    if not stale:
        print("No stale evidence found.")
        return
    for card, manifest, status in stale:
        print(f"- {card.evidence_id}")
        print(f"  client_id: {card.client_id}")
        print(f"  query_id: {card.query_id}")
        print(f"  status: {status}")
        print(f"  age_hours: {evidence_age_hours(card):.1f}")
        print(f"  freshness_sla_hours: {manifest.freshness_sla_hours}")


def print_mapping_section(title: str, mapping: dict[str, Any]) -> None:
    if not mapping:
        return
    print(f"{title}:")
    for key, value in sorted(mapping.items()):
        print(f"- {key}: {value}")


def print_list_section(title: str, values: list[str], *, heading_level: int = 0) -> None:
    if not values:
        return
    if heading_level:
        print(f"\n{'#' * heading_level} {title}\n")
    else:
        print(f"{title}:")
    for value in values:
        print(f"- {value}")
