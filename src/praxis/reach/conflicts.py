"""GTM-specific conflict checks for Reach evidence cards."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .manifests import QueryManifest
from .models import ClientCapsule


@dataclass(frozen=True)
class ConflictRecord:
    """Structured conflict evidence that can later map into Praxis Core."""

    conflict_id: str
    conflict_type: str
    severity: str
    status: str
    metric: str
    message: str
    sources: list[str] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)
    resolution: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def provider_kinds(capsule: ClientCapsule) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for kind, value in capsule.systems.items():
        if isinstance(value, dict) and value.get("provider"):
            kinds[str(value["provider"])] = kind
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("provider"):
                    kinds[str(item["provider"])] = kind
    return kinds


def detect_gtm_conflicts(
    *,
    capsule: ClientCapsule,
    manifest: QueryManifest,
    source_metrics: dict[str, dict[str, Any]],
) -> list[str]:
    return [record.message for record in detect_gtm_conflict_records(capsule=capsule, manifest=manifest, source_metrics=source_metrics)]


def detect_gtm_conflict_records(
    *,
    capsule: ClientCapsule,
    manifest: QueryManifest,
    source_metrics: dict[str, dict[str, Any]],
) -> list[ConflictRecord]:
    conflicts: list[ConflictRecord] = []
    kinds = provider_kinds(capsule)
    if "missing_crm_mapping" in manifest.conflict_checks:
        objects = capsule.field_map.get("objects", {})
        if "crm" in manifest.requires and not any(key in objects for key in ("contact", "opportunity")):
            conflicts.append(
                _record(
                    capsule,
                    manifest,
                    conflict_type="missing_crm_mapping",
                    severity="high",
                    metric="field_map",
                    message="missing_crm_mapping: CRM query requires contact or opportunity field mapping.",
                    sources=["crm"],
                    values={},
                )
            )

    if "crm_vs_ad_leads" in manifest.conflict_checks:
        crm_leads: list[float] = []
        ads_leads: list[float] = []
        for provider, metrics in source_metrics.items():
            if "leads" not in metrics:
                continue
            try:
                value = float(metrics["leads"])
            except (TypeError, ValueError):
                continue
            if kinds.get(provider) == "crm":
                crm_leads.append(value)
            elif kinds.get(provider) == "ads":
                ads_leads.append(value)
        if crm_leads and ads_leads:
            crm_total = sum(crm_leads)
            ads_total = sum(ads_leads)
            baseline = max(crm_total, 1.0)
            delta = abs(ads_total - crm_total) / baseline
            if delta >= 0.10:
                conflicts.append(
                    _record(
                        capsule,
                        manifest,
                        conflict_type="crm_vs_ad_leads",
                        severity="medium" if delta < 0.35 else "high",
                        metric="leads",
                        message=f"crm_vs_ad_leads: ad-platform leads ({ads_total:g}) differ from CRM leads ({crm_total:g}) by {delta:.0%}.",
                        sources=_providers_for_kind(kinds, "crm") + _providers_for_kind(kinds, "ads"),
                        values={"crm": crm_total, "ads": ads_total, "relative_delta": round(delta, 4)},
                    )
                )
    if "ads_vs_analytics_conversions" in manifest.conflict_checks:
        ads_conversions = _metric_values(source_metrics, kinds, "ads", "conversions")
        analytics_conversions = _metric_values(source_metrics, kinds, "analytics", "conversions")
        if ads_conversions and analytics_conversions:
            ads_total = sum(ads_conversions)
            analytics_total = sum(analytics_conversions)
            delta = _relative_delta(ads_total, analytics_total)
            if delta >= 0.20:
                conflicts.append(
                    _record(
                        capsule,
                        manifest,
                        conflict_type="ads_vs_analytics_conversions",
                        severity="medium" if delta < 0.50 else "high",
                        metric="conversions",
                        message=(
                            "ads_vs_analytics_conversions: Google Ads conversions "
                            f"({ads_total:g}) differ from analytics conversions ({analytics_total:g}) by {delta:.0%}."
                        ),
                        sources=_providers_for_kind(kinds, "ads") + _providers_for_kind(kinds, "analytics"),
                        values={"ads": ads_total, "analytics": analytics_total, "relative_delta": round(delta, 4)},
                    )
                )

    if "analytics_vs_crm_leads" in manifest.conflict_checks:
        analytics_conversions = _metric_values(source_metrics, kinds, "analytics", "conversions")
        if not analytics_conversions:
            analytics_conversions = _metric_values(source_metrics, kinds, "analytics", "key_events")
        crm_leads = _metric_values(source_metrics, kinds, "crm", "leads")
        if analytics_conversions and crm_leads:
            analytics_total = sum(analytics_conversions)
            crm_total = sum(crm_leads)
            delta = _relative_delta(analytics_total, crm_total)
            if delta >= 0.20:
                conflicts.append(
                    _record(
                        capsule,
                        manifest,
                        conflict_type="analytics_vs_crm_leads",
                        severity="medium" if delta < 0.50 else "high",
                        metric="leads",
                        message=(
                            "analytics_vs_crm_leads: analytics conversions/key events "
                            f"({analytics_total:g}) differ from CRM leads ({crm_total:g}) by {delta:.0%}."
                        ),
                        sources=_providers_for_kind(kinds, "analytics") + _providers_for_kind(kinds, "crm"),
                        values={"analytics": analytics_total, "crm": crm_total, "relative_delta": round(delta, 4)},
                    )
                )

    if "ad_spend_without_sessions" in manifest.conflict_checks:
        ad_spend = sum(_metric_values(source_metrics, kinds, "ads", "spend"))
        sessions = sum(_metric_values(source_metrics, kinds, "analytics", "sessions"))
        if ad_spend > 0 and sessions <= 0:
            conflicts.append(
                _record(
                    capsule,
                    manifest,
                    conflict_type="ad_spend_without_sessions",
                    severity="high",
                    metric="sessions",
                    message=f"ad_spend_without_sessions: ad spend is {ad_spend:g}, but analytics sessions are zero or unavailable.",
                    sources=_providers_for_kind(kinds, "ads") + _providers_for_kind(kinds, "analytics"),
                    values={"ad_spend": ad_spend, "sessions": sessions},
                )
            )
    return conflicts


def _metric_values(source_metrics: dict[str, dict[str, Any]], kinds: dict[str, str], kind: str, metric: str) -> list[float]:
    values: list[float] = []
    for provider, metrics in source_metrics.items():
        if kinds.get(provider) != kind or metric not in metrics:
            continue
        try:
            values.append(float(metrics[metric]))
        except (TypeError, ValueError):
            continue
    return values


def _relative_delta(left: float, right: float) -> float:
    return abs(left - right) / max(abs(right), 1.0)


def _providers_for_kind(kinds: dict[str, str], kind: str) -> list[str]:
    return sorted(provider for provider, provider_kind in kinds.items() if provider_kind == kind)


def _record(
    capsule: ClientCapsule,
    manifest: QueryManifest,
    *,
    conflict_type: str,
    severity: str,
    metric: str,
    message: str,
    sources: list[str],
    values: dict[str, Any],
) -> ConflictRecord:
    material = {
        "client_id": capsule.client_id,
        "query_id": manifest.manifest_id,
        "type": conflict_type,
        "metric": metric,
        "sources": sorted(set(sources)),
        "values": values,
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    return ConflictRecord(
        conflict_id=f"reach-conflict:{capsule.client_id}:{manifest.manifest_id}:{digest}",
        conflict_type=conflict_type,
        severity=severity,
        status="open",
        metric=metric,
        message=message,
        sources=sorted(set(sources)),
        values=values,
    )
