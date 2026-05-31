"""Query manifest loading for Praxis Reach."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .ontology import CANONICAL_METRICS
from .storage import manifests_dir, read_json, slug, write_json


@dataclass(frozen=True)
class QueryManifest:
    """A named, approved read-only query contract."""

    manifest_id: str
    description: str
    version: int = 1
    requires: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    storage_level: str = "aggregate_summary"
    pii_policy: str = "none"
    freshness_sla_hours: int = 24
    conflict_checks: list[str] = field(default_factory=list)
    source_priority: list[str] = field(default_factory=list)
    context_template: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueryManifest":
        return cls(
            manifest_id=str(data["id"]),
            description=str(data.get("description") or ""),
            version=int(data.get("version") or 1),
            requires=[str(item) for item in data.get("requires", [])],
            parameters=[str(item) for item in data.get("parameters", [])],
            outputs=[str(item) for item in data.get("outputs", [])],
            storage_level=str(data.get("storage_level") or "aggregate_summary"),
            pii_policy=str(data.get("pii_policy") or "none"),
            freshness_sla_hours=int(data.get("freshness_sla_hours") or 24),
            conflict_checks=[str(item) for item in data.get("conflict_checks", [])],
            source_priority=[str(item) for item in data.get("source_priority", [])],
            context_template=str(data.get("context_template") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.manifest_id,
            "description": self.description,
            "version": self.version,
            "requires": self.requires,
            "parameters": self.parameters,
            "outputs": self.outputs,
            "storage_level": self.storage_level,
            "pii_policy": self.pii_policy,
            "freshness_sla_hours": self.freshness_sla_hours,
            "conflict_checks": self.conflict_checks,
            "source_priority": self.source_priority,
            "context_template": self.context_template,
        }

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.manifest_id:
            errors.append("id is required")
        if not self.description:
            errors.append(f"{self.manifest_id}: description is required")
        if self.storage_level not in {"pointer", "metadata", "aggregate_summary", "redacted_sample"}:
            errors.append(f"{self.manifest_id}: unsupported storage_level {self.storage_level}")
        if self.pii_policy not in {"none", "redacted", "allowed"}:
            errors.append(f"{self.manifest_id}: unsupported pii_policy {self.pii_policy}")
        if self.pii_policy != "none" and self.storage_level != "redacted_sample":
            errors.append(f"{self.manifest_id}: non-none pii_policy requires redacted_sample storage")
        if self.freshness_sla_hours <= 0:
            errors.append(f"{self.manifest_id}: freshness_sla_hours must be positive")
        for output in self.outputs:
            if output not in CANONICAL_METRICS:
                errors.append(f"{self.manifest_id}: unknown canonical metric output {output}")
        return errors

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for parameter in self.parameters:
            if parameter not in params or params[parameter] in {None, ""}:
                errors.append(f"{self.manifest_id}: missing required parameter {parameter}")
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        if start_date or end_date:
            if not start_date or not end_date:
                errors.append(f"{self.manifest_id}: start_date and end_date must be provided together")
            else:
                try:
                    start = date.fromisoformat(str(start_date))
                    end = date.fromisoformat(str(end_date))
                except ValueError:
                    errors.append(f"{self.manifest_id}: start_date and end_date must use YYYY-MM-DD")
                else:
                    if start > end:
                        errors.append(f"{self.manifest_id}: start_date must be on or before end_date")
        return errors


def builtin_manifests() -> dict[str, QueryManifest]:
    manifests = [
        QueryManifest(
            manifest_id="pipeline_health",
            description="Compare lead flow, opportunities, and pipeline over a selected period.",
            requires=["crm"],
            parameters=["client_id", "start_date", "end_date"],
            outputs=["leads", "opportunities", "pipeline_amount", "closed_won_revenue"],
            conflict_checks=["missing_crm_mapping", "stale_source_warning"],
            source_priority=["crm"],
            context_template="pipeline_health_check",
        ),
        QueryManifest(
            manifest_id="reach_historical",
            description="Compare paid reach, spend, impressions, clicks, and leads over a selected period.",
            requires=["ads", "crm"],
            parameters=["client_id", "start_date", "end_date"],
            outputs=["spend", "reach", "impressions", "clicks", "conversions", "conversion_value", "conversion_rate", "leads"],
            conflict_checks=["crm_vs_ad_leads", "stale_source_warning"],
            source_priority=["crm", "ads"],
            context_template="reach_drop_diagnosis",
        ),
        QueryManifest(
            manifest_id="weekly_gtm_review",
            description="Build a compact cross-channel GTM review from live evidence.",
            requires=["crm", "ads"],
            parameters=["client_id", "start_date", "end_date"],
            outputs=["spend", "reach", "conversions", "leads", "opportunities", "pipeline_amount"],
            conflict_checks=["crm_vs_ad_leads", "stale_source_warning"],
            source_priority=["crm", "ads"],
            context_template="weekly_gtm_review",
        ),
        QueryManifest(
            manifest_id="website_performance",
            description="Pull aggregate GA4 website and conversion evidence over a selected period.",
            requires=["analytics"],
            parameters=["client_id", "start_date", "end_date"],
            outputs=["sessions", "active_users", "total_users", "event_count", "key_events", "conversions", "revenue", "engagement_rate", "conversion_rate"],
            conflict_checks=["stale_source_warning"],
            source_priority=["analytics"],
            context_template="weekly_gtm_review",
        ),
        QueryManifest(
            manifest_id="traffic_attribution_check",
            description="Compare paid traffic, analytics sessions, and platform conversions over a selected period.",
            requires=["ads", "analytics"],
            parameters=["client_id", "start_date", "end_date"],
            outputs=["spend", "impressions", "clicks", "sessions", "active_users", "conversions", "key_events", "conversion_value", "revenue", "conversion_rate"],
            conflict_checks=["ads_vs_analytics_conversions", "ad_spend_without_sessions", "stale_source_warning"],
            source_priority=["analytics", "ads"],
            context_template="reach_drop_diagnosis",
        ),
        QueryManifest(
            manifest_id="full_gtm_signal_check",
            description="Compare CRM, paid media, and analytics signals for a selected period.",
            requires=["crm", "ads", "analytics"],
            parameters=["client_id", "start_date", "end_date"],
            outputs=["spend", "clicks", "sessions", "conversions", "key_events", "leads", "opportunities", "pipeline_amount", "closed_won_revenue"],
            conflict_checks=["crm_vs_ad_leads", "ads_vs_analytics_conversions", "analytics_vs_crm_leads", "ad_spend_without_sessions", "stale_source_warning"],
            source_priority=["crm", "analytics", "ads"],
            context_template="weekly_gtm_review",
        ),
    ]
    return {manifest.manifest_id: manifest for manifest in manifests}


def manifest_path(root: Path, manifest_id: str) -> Path:
    return manifests_dir(root) / f"{slug(manifest_id)}.json"


def seed_builtin_manifests(root: Path) -> list[Path]:
    written: list[Path] = []
    for manifest in builtin_manifests().values():
        path = manifest_path(root, manifest.manifest_id)
        if not path.exists():
            write_json(path, manifest.to_dict())
            written.append(path)
    return written


def load_manifest(root: Path, manifest_id: str) -> QueryManifest:
    path = manifest_path(root, manifest_id)
    if path.exists():
        return QueryManifest.from_dict(read_json(path))
    builtins = builtin_manifests()
    if manifest_id in builtins:
        return builtins[manifest_id]
    raise KeyError(f"Unknown Reach query manifest: {manifest_id}")


def list_manifests(root: Path) -> list[QueryManifest]:
    manifests = dict(builtin_manifests())
    if manifests_dir(root).exists():
        for path in sorted(manifests_dir(root).glob("*.json")):
            manifest = QueryManifest.from_dict(read_json(path))
            manifests[manifest.manifest_id] = manifest
    return [manifests[key] for key in sorted(manifests)]


def validate_manifests(root: Path) -> list[str]:
    errors: list[str] = []
    for manifest in list_manifests(root):
        errors.extend(manifest.validate())
    return errors
