"""Canonical GTM objects and metrics for Praxis Reach."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .storage import ontology_dir, write_json


CANONICAL_OBJECTS: dict[str, dict[str, Any]] = {
    "contact": {
        "description": "A person, lead, prospect, subscriber, or customer contact.",
        "required_fields": ["id"],
        "common_sources": ["hubspot.contacts", "fixture_crm.contacts", "mock_crm.contacts"],
    },
    "company": {
        "description": "An organization, account, company, or customer entity.",
        "required_fields": ["id"],
        "common_sources": ["hubspot.companies", "fixture_crm.companies", "mock_crm.companies"],
    },
    "opportunity": {
        "description": "A deal, sales opportunity, pipeline item, or revenue opportunity.",
        "required_fields": ["id", "amount", "stage"],
        "common_sources": ["hubspot.deals", "fixture_crm.opportunities", "mock_crm.opportunities"],
    },
    "campaign": {
        "description": "A marketing or advertising campaign.",
        "required_fields": ["id", "name"],
        "common_sources": ["google_ads.campaigns", "meta_ads.campaigns", "hubspot.campaigns"],
    },
    "ad_group": {
        "description": "A campaign subdivision such as a Google Ads ad group or Meta ad set.",
        "required_fields": ["id", "name"],
        "common_sources": ["google_ads.ad_groups", "meta_ads.ad_sets"],
    },
    "ad": {
        "description": "An individual ad, creative, or promoted unit.",
        "required_fields": ["id", "name"],
        "common_sources": ["google_ads.ads", "meta_ads.ads"],
    },
    "metric_snapshot": {
        "description": "A time-bounded aggregate measurement from a source system.",
        "required_fields": ["date"],
        "common_sources": ["google_ads.metrics", "meta_ads.insights", "ga4.events"],
    },
    "web_property": {
        "description": "A website or app analytics property.",
        "required_fields": ["id"],
        "common_sources": ["google_analytics.properties"],
    },
    "traffic_channel": {
        "description": "A web analytics traffic channel, source, medium, or campaign grouping.",
        "required_fields": ["id", "name"],
        "common_sources": ["google_analytics.channels"],
    },
    "landing_page": {
        "description": "A website landing page or entry path used for campaign and funnel analysis.",
        "required_fields": ["path"],
        "common_sources": ["google_analytics.landing_pages"],
    },
}


CANONICAL_METRICS: dict[str, dict[str, Any]] = {
    "spend": {"object": "metric_snapshot", "description": "Paid media cost in client currency."},
    "reach": {"object": "metric_snapshot", "description": "Unique people reached where available."},
    "impressions": {"object": "metric_snapshot", "description": "Total ad impressions."},
    "clicks": {"object": "metric_snapshot", "description": "Total ad clicks."},
    "ctr": {"object": "metric_snapshot", "description": "Clicks divided by impressions."},
    "cpc": {"object": "metric_snapshot", "description": "Spend divided by clicks."},
    "cpm": {"object": "metric_snapshot", "description": "Spend per thousand impressions."},
    "conversions": {"object": "metric_snapshot", "description": "Platform-reported conversions or key events."},
    "conversion_value": {"object": "metric_snapshot", "description": "Platform-reported conversion value."},
    "leads": {"object": "contact", "description": "New leads created in the selected period."},
    "mqls": {"object": "contact", "description": "Marketing-qualified leads by client definition."},
    "sqls": {"object": "contact", "description": "Sales-qualified leads by client definition."},
    "opportunities": {"object": "opportunity", "description": "Opportunities created in the selected period."},
    "pipeline_amount": {"object": "opportunity", "description": "Pipeline value in client currency."},
    "closed_won_revenue": {"object": "opportunity", "description": "Closed-won revenue in client currency."},
    "sessions": {"object": "metric_snapshot", "description": "Website or app sessions."},
    "active_users": {"object": "metric_snapshot", "description": "Active users reported by analytics."},
    "total_users": {"object": "metric_snapshot", "description": "Total users reported by analytics."},
    "event_count": {"object": "metric_snapshot", "description": "Analytics event count."},
    "key_events": {"object": "metric_snapshot", "description": "GA4 key events or similar high-value actions."},
    "revenue": {"object": "metric_snapshot", "description": "Analytics-attributed revenue."},
    "engagement_rate": {"object": "metric_snapshot", "description": "Engaged sessions divided by sessions where available."},
    "cac": {"object": "metric_snapshot", "description": "Customer acquisition cost."},
    "roas": {"object": "metric_snapshot", "description": "Revenue attributed to ad spend divided by spend."},
    "conversion_rate": {"object": "metric_snapshot", "description": "Conversions divided by the relevant traffic or lead base."},
}


def default_field_map(crm: str = "mock_crm", ads: str = "mock_ads", analytics: str | None = None) -> dict[str, Any]:
    contact_fields = {
        "id": "id",
        "created_at": "created_at",
        "lifecycle_stage": "lifecycle_stage",
        "source": "source",
    }
    opportunity_source = f"{crm}.opportunities"
    opportunity_fields = {
        "id": "id",
        "created_at": "created_at",
        "amount": "amount",
        "stage": "stage",
        "close_date": "close_date",
        "source": "source",
    }
    if crm == "hubspot":
        contact_fields = {
            "id": "hs_object_id",
            "created_at": "createdate",
            "lifecycle_stage": "lifecyclestage",
            "source": "hs_analytics_source",
        }
        opportunity_source = "hubspot.deals"
        opportunity_fields = {
            "id": "hs_object_id",
            "created_at": "createdate",
            "amount": "amount",
            "stage": "dealstage",
            "close_date": "closedate",
            "pipeline": "pipeline",
            "source": "hubspot_owner_id",
        }
    objects: dict[str, Any] = {
        "contact": {
            "source": f"{crm}.contacts",
            "fields": contact_fields,
        },
        "opportunity": {
            "source": opportunity_source,
            "fields": opportunity_fields,
        },
        "campaign": {
            "source": f"{ads}.campaigns",
            "fields": {
                "id": "id",
                "name": "name",
                "channel": "channel",
                "status": "status",
            },
        },
        "metric_snapshot": {
            "source": f"{ads}.metric_snapshots",
            "fields": {
                "date": "date",
                "spend": "spend",
                "reach": "reach",
                "impressions": "impressions",
                "clicks": "clicks",
            },
        },
    }
    if analytics:
        objects.update(
            {
                "web_property": {
                    "source": f"{analytics}.properties",
                    "fields": {"id": "property_id", "name": "display_name"},
                },
                "traffic_channel": {
                    "source": f"{analytics}.channels",
                    "fields": {"id": "sessionDefaultChannelGroup", "name": "sessionDefaultChannelGroup"},
                },
                "landing_page": {
                    "source": f"{analytics}.landing_pages",
                    "fields": {"path": "landingPagePlusQueryString"},
                },
            }
        )
    return {
        "version": 1,
        "objects": objects,
    }


def default_metric_definitions(analytics: str | None = None) -> dict[str, Any]:
    analytics_metrics = {"sessions", "active_users", "total_users", "event_count", "key_events", "revenue", "engagement_rate"}

    def source_priority(metric: str) -> list[str]:
        if analytics and metric in analytics_metrics:
            return ["analytics", "ads", "crm"]
        if metric in {"leads", "pipeline_amount", "opportunities", "closed_won_revenue", "mqls", "sqls"}:
            return ["crm", "ads"]
        return ["ads", "crm"]

    return {
        "version": 1,
        "metrics": {
            metric: {
                "canonical_object": spec["object"],
                "description": spec["description"],
                "source_priority": source_priority(metric),
            }
            for metric, spec in CANONICAL_METRICS.items()
        },
    }


def seed_ontology(root: Path) -> list[Path]:
    written: list[Path] = []
    targets = {
        "objects.json": {"objects": CANONICAL_OBJECTS},
        "metrics.json": {"metrics": CANONICAL_METRICS},
    }
    for filename, data in targets.items():
        path = ontology_dir(root) / filename
        if not path.exists():
            write_json(path, data)
            written.append(path)
    return written


def validate_field_map(field_map: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    objects = field_map.get("objects")
    if not isinstance(objects, dict):
        return ["field_map.objects must be an object"]
    for object_id, mapping in objects.items():
        if object_id not in CANONICAL_OBJECTS:
            errors.append(f"unknown canonical object: {object_id}")
            continue
        if not isinstance(mapping, dict):
            errors.append(f"{object_id} mapping must be an object")
            continue
        fields = mapping.get("fields")
        if not isinstance(fields, dict):
            errors.append(f"{object_id}.fields must be an object")
            continue
        for required in CANONICAL_OBJECTS[object_id]["required_fields"]:
            if required not in fields:
                errors.append(f"{object_id}.fields missing required field: {required}")
    return errors


def validate_metric_definitions(metrics: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    metric_map = metrics.get("metrics", metrics)
    if not isinstance(metric_map, dict):
        return ["metrics must be an object"]
    for metric_id, definition in metric_map.items():
        if metric_id not in CANONICAL_METRICS:
            errors.append(f"unknown canonical metric: {metric_id}")
            continue
        if isinstance(definition, dict):
            canonical_object = definition.get("canonical_object")
            if canonical_object and canonical_object not in CANONICAL_OBJECTS:
                errors.append(f"{metric_id} uses unknown canonical_object: {canonical_object}")
    return errors
