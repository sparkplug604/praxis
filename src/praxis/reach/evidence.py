"""Evidence cards for source-linked live operational query results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .connectors.base import ConnectorResult
from .conflicts import ConflictRecord, detect_gtm_conflict_records, provider_kinds
from .manifests import QueryManifest
from .models import ClientCapsule
from .storage import evidence_dir, reach_conflicts_dir, read_json, slug, write_json


@dataclass(frozen=True)
class EvidenceCard:
    evidence_id: str
    query_id: str
    client_id: str
    fresh_at: str
    sources: list[str]
    source_links: list[str]
    summary: str
    metrics: dict[str, Any]
    metric_sources: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    source_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    source_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    manifest_version: int = 1
    freshness_status: str = "fresh"
    connector_versions: dict[str, str] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    conflict_records: list[dict[str, Any]] = field(default_factory=list)
    metric_lineage: dict[str, dict[str, Any]] = field(default_factory=dict)
    partial_data: bool = False
    data_quality_status: str = "ok"
    confidence_score: float = 1.0
    redaction_status: str = "not_required"
    warnings: list[str] = field(default_factory=list)
    row_count: int = 0
    storage_level: str = "aggregate_summary"
    query_hash: str = ""
    artifact_schema_version: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceCard":
        return cls(
            artifact_schema_version=int(data.get("artifact_schema_version") or data.get("schema_version") or 1),
            evidence_id=str(data["evidence_id"]),
            query_id=str(data["query_id"]),
            client_id=str(data["client_id"]),
            fresh_at=str(data["fresh_at"]),
            sources=[str(item) for item in data.get("sources", [])],
            source_links=[str(item) for item in data.get("source_links", [])],
            summary=str(data.get("summary") or ""),
            metrics=dict(data.get("metrics") or {}),
            metric_sources={str(key): str(value) for key, value in dict(data.get("metric_sources") or {}).items()},
            params=dict(data.get("params") or {}),
            source_metrics={
                str(key): dict(value)
                for key, value in dict(data.get("source_metrics") or {}).items()
                if isinstance(value, dict)
            },
            source_metadata={
                str(key): dict(value)
                for key, value in dict(data.get("source_metadata") or {}).items()
                if isinstance(value, dict)
            },
            manifest_version=int(data.get("manifest_version") or 1),
            freshness_status=str(data.get("freshness_status") or "fresh"),
            connector_versions={str(key): str(value) for key, value in dict(data.get("connector_versions") or {}).items()},
            conflicts=[str(item) for item in data.get("conflicts", [])],
            conflict_records=[dict(item) for item in data.get("conflict_records", []) if isinstance(item, dict)],
            metric_lineage={
                str(key): dict(value)
                for key, value in dict(data.get("metric_lineage") or {}).items()
                if isinstance(value, dict)
            },
            partial_data=bool(data.get("partial_data", False)),
            data_quality_status=str(data.get("data_quality_status") or "ok"),
            confidence_score=float(data.get("confidence_score", 1.0)),
            redaction_status=str(data.get("redaction_status") or "not_required"),
            warnings=[str(item) for item in data.get("warnings", [])],
            row_count=int(data.get("row_count") or 0),
            storage_level=str(data.get("storage_level") or "aggregate_summary"),
            query_hash=str(data.get("query_hash") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_schema_version": self.artifact_schema_version,
            "evidence_id": self.evidence_id,
            "query_id": self.query_id,
            "client_id": self.client_id,
            "fresh_at": self.fresh_at,
            "sources": self.sources,
            "source_links": self.source_links,
            "summary": self.summary,
            "metrics": self.metrics,
            "metric_sources": self.metric_sources,
            "params": self.params,
            "source_metrics": self.source_metrics,
            "source_metadata": self.source_metadata,
            "manifest_version": self.manifest_version,
            "freshness_status": self.freshness_status,
            "connector_versions": self.connector_versions,
            "conflicts": self.conflicts,
            "conflict_records": self.conflict_records,
            "metric_lineage": self.metric_lineage,
            "partial_data": self.partial_data,
            "data_quality_status": self.data_quality_status,
            "confidence_score": self.confidence_score,
            "redaction_status": self.redaction_status,
            "warnings": self.warnings,
            "row_count": self.row_count,
            "storage_level": self.storage_level,
            "query_hash": self.query_hash,
        }


def evidence_path(root: Path, evidence_id: str) -> Path:
    return evidence_dir(root) / f"{slug(evidence_id.replace(':', '-'))}.json"


def conflict_record_path(root: Path, conflict_id: str) -> Path:
    return reach_conflicts_dir(root) / f"{slug(conflict_id.replace(':', '-'))}.json"


def compute_query_hash(manifest: QueryManifest, params: dict[str, Any]) -> str:
    material = json.dumps(
        {"manifest": manifest.to_dict(), "params": params},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def _metric_rank(capsule: ClientCapsule, manifest: QueryManifest, provider: str) -> tuple[int, str]:
    kinds = provider_kinds(capsule)
    kind = kinds.get(provider, provider)
    if kind in manifest.source_priority:
        return (manifest.source_priority.index(kind), provider)
    if provider in manifest.source_priority:
        return (manifest.source_priority.index(provider), provider)
    return (len(manifest.source_priority), provider)


def _merge_metrics_by_source_priority(
    capsule: ClientCapsule,
    manifest: QueryManifest,
    results: list[ConnectorResult],
) -> tuple[dict[str, Any], dict[str, str], dict[str, dict[str, Any]]]:
    metrics: dict[str, Any] = {}
    metric_sources: dict[str, str] = {}
    candidates: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        for metric, value in result.metrics.items():
            candidates.setdefault(metric, []).append(
                {
                    "provider": result.provider,
                    "provider_kind": provider_kinds(capsule).get(result.provider, result.provider),
                    "value": value,
                    "rank": _metric_rank(capsule, manifest, result.provider)[0],
                }
            )
            current_provider = metric_sources.get(metric)
            if current_provider is None or _metric_rank(capsule, manifest, result.provider) < _metric_rank(capsule, manifest, current_provider):
                metrics[metric] = value
                metric_sources[metric] = result.provider
    lineage = {
        metric: {
            "selected_provider": metric_sources.get(metric, ""),
            "selected_value": metrics.get(metric),
            "selection_rule": "manifest.source_priority",
            "candidates": sorted(values, key=lambda item: (item["rank"], item["provider"])),
        }
        for metric, values in candidates.items()
    }
    return metrics, metric_sources, lineage


def _data_quality(conflict_records: list[ConflictRecord], partial_data: bool) -> tuple[str, float]:
    open_records = [record for record in conflict_records if record.status in {"open", "acknowledged"}]
    high_conflicts = [record for record in open_records if record.severity == "high"]
    if partial_data and high_conflicts:
        return "partial_conflicted", 0.35
    if high_conflicts:
        return "conflicted", 0.50
    if open_records:
        return ("partial_conflicted" if partial_data else "conflicted", 0.70 if not partial_data else 0.55)
    if partial_data:
        return "partial", 0.75
    return "ok", 1.0


def create_evidence_card(
    root: Path,
    capsule: ClientCapsule,
    manifest: QueryManifest,
    params: dict[str, Any],
    results: list[ConnectorResult],
) -> EvidenceCard:
    fresh_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    digest = compute_query_hash(manifest, params)
    timestamp_id = fresh_at.replace("+00:00", "Z").replace(":", "").replace("-", "").replace(".", "")
    run_id = f"{timestamp_id}-{uuid4().hex[:8]}"
    evidence_id = f"ev:{manifest.manifest_id}:{capsule.client_id}:{run_id}:{digest}"
    metrics, metric_sources, metric_lineage = _merge_metrics_by_source_priority(capsule, manifest, results)
    source_links: list[str] = []
    warnings: list[str] = []
    summaries: list[str] = []
    row_count = 0
    sources: list[str] = []
    connector_versions: dict[str, str] = {}
    conflicts: list[str] = []
    source_metrics: dict[str, dict[str, Any]] = {}
    source_metadata: dict[str, dict[str, Any]] = {}
    partial_data = False
    for result in results:
        sources.append(result.provider)
        connector_versions[result.provider] = str(result.metadata.get("connector_version") or "unknown")
        source_metrics[result.provider] = dict(result.metrics)
        source_metadata[result.provider] = dict(result.metadata)
        partial_data = partial_data or bool(result.metadata.get("partial_data"))
        source_links.extend(result.source_links)
        warnings.extend(result.warnings)
        conflicts.extend(str(item) for item in result.metadata.get("conflicts", []))
        summaries.append(result.summary)
        row_count += result.row_count
    detected_conflicts = detect_gtm_conflict_records(capsule=capsule, manifest=manifest, source_metrics=source_metrics)
    conflicts.extend(record.message for record in detected_conflicts)
    data_quality_status, confidence_score = _data_quality(detected_conflicts, partial_data)
    if manifest.pii_policy == "none":
        redaction_status = "not_required"
    else:
        redaction_status = "redacted"
    card = EvidenceCard(
        evidence_id=evidence_id,
        query_id=manifest.manifest_id,
        client_id=capsule.client_id,
        fresh_at=fresh_at,
        sources=sources,
        source_links=source_links,
        summary=" ".join(summaries),
        metrics=metrics,
        metric_sources=metric_sources,
        params=params,
        source_metrics=source_metrics,
        source_metadata=source_metadata,
        manifest_version=manifest.version,
        freshness_status="fresh",
        connector_versions=connector_versions,
        conflicts=sorted(set(conflicts)),
        conflict_records=[record.to_dict() for record in detected_conflicts],
        metric_lineage=metric_lineage,
        partial_data=partial_data,
        data_quality_status=data_quality_status,
        confidence_score=confidence_score,
        redaction_status=redaction_status,
        warnings=warnings,
        row_count=row_count,
        storage_level=manifest.storage_level,
        query_hash=digest,
    )
    write_json(evidence_path(root, evidence_id), card.to_dict())
    for record in detected_conflicts:
        payload = record.to_dict()
        payload.update(
            {
                "artifact_schema_version": 1,
                "evidence_id": evidence_id,
                "query_id": manifest.manifest_id,
                "client_id": capsule.client_id,
                "detected_at": fresh_at,
            }
        )
        write_json(conflict_record_path(root, record.conflict_id), payload)
    return card


def list_evidence(root: Path, client_id: str | None = None) -> list[EvidenceCard]:
    cards: list[EvidenceCard] = []
    if not evidence_dir(root).exists():
        return cards
    for path in sorted(evidence_dir(root).glob("*.json")):
        card = EvidenceCard.from_dict(read_json(path))
        if client_id and card.client_id != client_id:
            continue
        cards.append(card)
    return cards


def load_evidence(root: Path, evidence_id: str) -> EvidenceCard:
    direct = evidence_path(root, evidence_id)
    if direct.exists():
        return EvidenceCard.from_dict(read_json(direct))
    for path in evidence_dir(root).glob("*.json"):
        card = EvidenceCard.from_dict(read_json(path))
        if card.evidence_id == evidence_id:
            return card
    raise KeyError(f"Unknown evidence card: {evidence_id}")


def latest_evidence(root: Path, client_id: str, query_id: str | None = None) -> EvidenceCard | None:
    cards = [
        card
        for card in list_evidence(root, client_id=client_id)
        if query_id is None or card.query_id == query_id
    ]
    if not cards:
        return None
    return sorted(cards, key=lambda card: card.fresh_at)[-1]
