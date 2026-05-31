"""Read-only HubSpot connector for Praxis Reach."""

from __future__ import annotations

import re
from typing import Any, Callable

from .base import ConnectorCheck, ConnectorResult, env_value_with_fallback, system_config
from .hubspot_client import HubSpotClient, HubSpotClientError, HubSpotPage
from praxis.reach.manifests import QueryManifest
from praxis.reach.models import ClientCapsule


DEFAULT_MQL_STAGES = {"marketingqualifiedlead", "mql"}
DEFAULT_SQL_STAGES = {"salesqualifiedlead", "sql"}
DEFAULT_CLOSED_WON_STAGES = {"closedwon", "closed_won", "closed won"}
DEFAULT_CLOSED_LOST_STAGES = {"closedlost", "closed_lost", "closed lost"}


class HubSpotConnector:
    provider = "hubspot"
    connector_version = "hubspot-2026-03-readonly-v1"

    def __init__(self, client_factory: Callable[[str], HubSpotClient] = HubSpotClient) -> None:
        self.client_factory = client_factory

    def capabilities(self) -> dict[str, Any]:
        return {
            "kind": "crm",
            "mode": "read_only",
            "auth": "client-specific HubSpot private app token or OAuth access token reference",
            "api_version": HubSpotClient.api_version,
            "objects": ["contact", "company", "opportunity"],
            "hubspot_objects": ["contacts", "companies", "deals"],
            "metrics": ["leads", "mqls", "sqls", "opportunities", "pipeline_amount", "closed_won_revenue"],
            "supports_deep_links": True,
            "storage_levels": ["metadata", "aggregate_summary"],
            "status": "experimental",
            "live_setup_check": True,
        }

    def list_resources(self, capsule: ClientCapsule) -> list[str]:
        return ["contacts", "companies", "deals"]

    def introspect_schema(self, capsule: ClientCapsule) -> dict[str, Any]:
        return {
            "contacts": _object_fields(capsule, "contact", _default_contact_fields()),
            "deals": _object_fields(capsule, "opportunity", _default_deal_fields()),
        }

    def credential_env(self, capsule: ClientCapsule) -> tuple[str, str]:
        config = system_config(capsule, self.provider)
        return env_value_with_fallback(config, "credential_env", "fallback_credential_env", "HUBSPOT_ACCESS_TOKEN")

    def check_setup(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorCheck:
        env_name, token = self.credential_env(capsule)
        if not token:
            return ConnectorCheck(
                provider=self.provider,
                status="missing_credentials",
                message=f"Set {env_name} for client {capsule.client_id}, or configure credential_env in systems.json.",
                details={"credential_env": env_name, "api_version": HubSpotClient.api_version},
            )
        details = {
            "credential_env": env_name,
            "mode": "read_only",
            "api_version": HubSpotClient.api_version,
            "auth_mode": _auth_mode(capsule),
        }
        if not live:
            return ConnectorCheck(
                provider=self.provider,
                status="configured",
                message="HubSpot token env var is present. Add --live to verify HubSpot API access.",
                details=details,
                warnings=["Static setup checks do not call HubSpot; they only verify local credential configuration."],
            )
        try:
            fields = _object_fields(capsule, "contact", _default_contact_fields())
            config = system_config(capsule, self.provider)
            self._client(token, config).collect_search(
                "contacts",
                filters=[],
                properties=[fields["id"]],
                limit=1,
                max_pages=1,
            )
        except HubSpotClientError as exc:
            return ConnectorCheck(
                provider=self.provider,
                status="api_error",
                message=str(exc),
                details=details,
            )
        return ConnectorCheck(
            provider=self.provider,
            status="ok",
            message="HubSpot token and CRM object search access verified.",
            details=details,
        )

    def run_query(self, capsule: ClientCapsule, manifest: QueryManifest, params: dict[str, Any]) -> ConnectorResult:
        env_name, token = self.credential_env(capsule)
        if not token:
            raise RuntimeError(f"HubSpot connector requires {env_name} and read-only CRM scopes.")
        start_date = str(params.get("start_date") or "")
        end_date = str(params.get("end_date") or "")
        if not start_date or not end_date:
            raise RuntimeError("HubSpot connector requires start_date and end_date query params.")

        config = system_config(capsule, self.provider)
        max_pages = int(config.get("max_pages") or 50)
        client = self._client(token, config)
        contact_fields = _object_fields(capsule, "contact", _default_contact_fields())
        deal_fields = _object_fields(capsule, "opportunity", _default_deal_fields())

        contact_page = client.collect_search(
            "contacts",
            filters=_between_filter(contact_fields["created_at"], start_date, end_date),
            properties=_unique([contact_fields["id"], contact_fields["created_at"], contact_fields["lifecycle_stage"], contact_fields["source"]]),
            max_pages=max_pages,
        )
        created_deal_page = client.collect_search(
            "deals",
            filters=_between_filter(deal_fields["created_at"], start_date, end_date),
            properties=_unique(
                [
                    deal_fields["id"],
                    deal_fields["created_at"],
                    deal_fields["amount"],
                    deal_fields["stage"],
                    deal_fields["close_date"],
                    deal_fields.get("pipeline", "pipeline"),
                ]
            ),
            max_pages=max_pages,
        )
        closed_deal_page = client.collect_search(
            "deals",
            filters=_between_filter(deal_fields["close_date"], start_date, end_date),
            properties=_unique(
                [
                    deal_fields["id"],
                    deal_fields["amount"],
                    deal_fields["stage"],
                    deal_fields["close_date"],
                    deal_fields.get("pipeline", "pipeline"),
                ]
            ),
            max_pages=max_pages,
        )

        metrics = _aggregate_metrics(capsule, contact_page, created_deal_page, closed_deal_page, contact_fields, deal_fields)
        warnings = [
            "HubSpot metrics are aggregate summaries; Praxis does not store raw contact or deal rows.",
            "Confirm lifecycle and pipeline definitions in metrics.json before treating MQL/SQL/stage metrics as canonical.",
        ]
        for object_type, page in {
            "contacts": contact_page,
            "deals_created": created_deal_page,
            "deals_closed": closed_deal_page,
        }.items():
            if page.truncated:
                warnings.append(f"HubSpot {object_type} search reached max_pages={max_pages}; returned metrics may be partial.")

        row_count = len(contact_page.rows) + len(created_deal_page.rows) + len(closed_deal_page.rows)
        partial_data = contact_page.truncated or created_deal_page.truncated or closed_deal_page.truncated
        return ConnectorResult(
            provider=self.provider,
            summary=(
                f"HubSpot scanned {len(contact_page.rows)} contacts, {len(created_deal_page.rows)} created deals, "
                f"and {len(closed_deal_page.rows)} closed-date deals for {capsule.client_id} from {start_date} to {end_date}."
            ),
            metrics={key: value for key, value in metrics.items() if key in manifest.outputs},
            source_links=[_hubspot_home_link(config)],
            warnings=warnings,
            row_count=row_count,
            metadata={
                "connector_version": self.connector_version,
                "api_version": HubSpotClient.api_version,
                "params": params,
                "partial_data": partial_data,
                "completeness": "partial" if partial_data else "complete",
                "credential_env": env_name,
                "auth_mode": _auth_mode(capsule),
                "row_storage": "none",
                "max_pages": max_pages,
                "pages_read": {
                    "contacts": contact_page.pages_read,
                    "deals_created": created_deal_page.pages_read,
                    "deals_closed": closed_deal_page.pages_read,
                },
                "field_map": {
                    "contact": contact_fields,
                    "opportunity": deal_fields,
                },
            },
        )

    def _client(self, token: str, config: dict[str, Any]) -> HubSpotClient:
        max_retries = int(config.get("max_retries") or 3)
        try:
            return self.client_factory(token, max_retries=max_retries)
        except TypeError:
            return self.client_factory(token)


def _aggregate_metrics(
    capsule: ClientCapsule,
    contact_page: HubSpotPage,
    created_deal_page: HubSpotPage,
    closed_deal_page: HubSpotPage,
    contact_fields: dict[str, str],
    deal_fields: dict[str, str],
) -> dict[str, float | int]:
    mql_stages = _metric_stage_values(capsule, "mqls", DEFAULT_MQL_STAGES)
    sql_stages = _metric_stage_values(capsule, "sqls", DEFAULT_SQL_STAGES)
    closed_won_stages = _metric_stage_values(capsule, "closed_won_revenue", DEFAULT_CLOSED_WON_STAGES)
    metrics: dict[str, float | int] = {
        "leads": len(contact_page.rows),
        "mqls": sum(1 for row in contact_page.rows if _norm(_prop(row, contact_fields["lifecycle_stage"])) in mql_stages),
        "sqls": sum(1 for row in contact_page.rows if _norm(_prop(row, contact_fields["lifecycle_stage"])) in sql_stages),
        "opportunities": len(created_deal_page.rows),
        "pipeline_amount": 0.0,
        "closed_won_revenue": 0.0,
    }
    for row in created_deal_page.rows:
        stage = _norm(_prop(row, deal_fields["stage"]))
        if stage in DEFAULT_CLOSED_LOST_STAGES:
            continue
        metrics["pipeline_amount"] = float(metrics["pipeline_amount"]) + _money(_prop(row, deal_fields["amount"]))
    for row in closed_deal_page.rows:
        stage = _norm(_prop(row, deal_fields["stage"]))
        if stage in closed_won_stages:
            metrics["closed_won_revenue"] = float(metrics["closed_won_revenue"]) + _money(_prop(row, deal_fields["amount"]))
    metrics["pipeline_amount"] = round(float(metrics["pipeline_amount"]), 2)
    metrics["closed_won_revenue"] = round(float(metrics["closed_won_revenue"]), 2)
    return metrics


def _object_fields(capsule: ClientCapsule, object_id: str, defaults: dict[str, str]) -> dict[str, str]:
    objects = capsule.field_map.get("objects") if isinstance(capsule.field_map, dict) else None
    mapping = objects.get(object_id) if isinstance(objects, dict) else None
    fields = mapping.get("fields") if isinstance(mapping, dict) else None
    if not isinstance(fields, dict):
        return dict(defaults)
    merged = dict(defaults)
    merged.update({str(key): str(value) for key, value in fields.items()})
    return merged


def _default_contact_fields() -> dict[str, str]:
    return {
        "id": "hs_object_id",
        "created_at": "createdate",
        "lifecycle_stage": "lifecyclestage",
        "source": "hs_analytics_source",
    }


def _default_deal_fields() -> dict[str, str]:
    return {
        "id": "hs_object_id",
        "created_at": "createdate",
        "amount": "amount",
        "stage": "dealstage",
        "close_date": "closedate",
        "pipeline": "pipeline",
        "source": "hubspot_owner_id",
    }


def _between_filter(property_name: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    return [
        {
            "propertyName": property_name,
            "operator": "BETWEEN",
            "value": f"{start_date}T00:00:00Z",
            "highValue": f"{end_date}T23:59:59Z",
        }
    ]


def _prop(row: dict[str, Any], property_name: str) -> str:
    properties = row.get("properties")
    if isinstance(properties, dict):
        value = properties.get(property_name)
        if value not in {None, ""}:
            return str(value)
    if property_name in {"id", "hs_object_id"} and row.get("id") not in {None, ""}:
        return str(row["id"])
    return ""


def _money(value: str) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _metric_stage_values(capsule: ClientCapsule, metric_id: str, defaults: set[str]) -> set[str]:
    metric_map = capsule.metrics.get("metrics", capsule.metrics)
    definition = metric_map.get(metric_id) if isinstance(metric_map, dict) else None
    values: set[str] = set()
    if isinstance(definition, dict):
        configured = definition.get("stage_values")
        if isinstance(configured, list):
            values.update(_norm(str(item)) for item in configured)
        text = str(definition.get("definition") or "")
        values.update(_stage_values_from_text(text))
    return values or {_norm(item) for item in defaults}


def _stage_values_from_text(text: str) -> set[str]:
    if not text:
        return set()
    values: set[str] = set()
    for match in re.finditer(r"==\s*['\"]?([A-Za-z0-9_ -]+)['\"]?", text):
        values.add(_norm(match.group(1)))
    for match in re.finditer(r"\bin\s*\[([^\]]+)\]", text):
        for item in match.group(1).split(","):
            cleaned = item.strip().strip("'\"")
            if cleaned:
                values.add(_norm(cleaned))
    return values


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _auth_mode(capsule: ClientCapsule) -> str:
    config = system_config(capsule, HubSpotConnector.provider)
    return str(config.get("auth_mode") or "static_token")


def _hubspot_home_link(config: dict[str, Any]) -> str:
    portal_id = config.get("portal_id") or config.get("hub_id")
    if portal_id:
        return f"https://app.hubspot.com/contacts/{portal_id}/objects/0-1/views/all/list"
    return "https://app.hubspot.com/"
