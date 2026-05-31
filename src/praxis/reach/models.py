"""Shared data models for Praxis Reach and agency client capsules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_POLICIES = {
    "mode": "read_only",
    "pii_storage": "none",
    "aggregate_cache": "allowed",
    "row_cache": "disallowed",
    "freshness_sla_hours": 24,
    "allowed_storage_levels": ["pointer", "metadata", "aggregate_summary"],
    "writeback": "disabled",
}


@dataclass(frozen=True)
class ClientCapsule:
    """A per-client operating contract for live GTM context."""

    client_id: str
    name: str
    timezone: str = "UTC"
    currency: str = "USD"
    systems: dict[str, Any] = field(default_factory=dict)
    policies: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_POLICIES))
    metrics: dict[str, Any] = field(default_factory=dict)
    field_map: dict[str, Any] = field(default_factory=dict)
    permissions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClientCapsule":
        client = data.get("client", {})
        return cls(
            client_id=str(client.get("id") or data.get("client_id") or ""),
            name=str(client.get("name") or data.get("name") or client.get("id") or ""),
            timezone=str(client.get("timezone") or "UTC"),
            currency=str(client.get("currency") or "USD"),
            systems=dict(data.get("systems") or {}),
            policies={**DEFAULT_POLICIES, **dict(data.get("policies") or {})},
            metrics=dict(data.get("metrics") or {}),
            field_map=dict(data.get("field_map") or {}),
            permissions={**DEFAULT_POLICIES, **dict(data.get("permissions") or data.get("policies") or {})},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "client": {
                "id": self.client_id,
                "name": self.name,
                "timezone": self.timezone,
                "currency": self.currency,
            },
            "systems": self.systems,
            "policies": self.policies,
            "metrics": self.metrics,
            "field_map": self.field_map,
            "permissions": self.permissions,
        }

    def providers(self) -> list[str]:
        out: list[str] = []
        for value in self.systems.values():
            if isinstance(value, dict):
                provider = value.get("provider")
                if provider:
                    out.append(str(provider))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get("provider"):
                        out.append(str(item["provider"]))
        return out


def env_slug(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value.upper()).strip("_") or "CLIENT"


def crm_system(provider: str, client_id: str = "") -> dict[str, Any]:
    config: dict[str, Any] = {
        "provider": provider,
        "source_of_truth_for": ["contacts", "opportunities", "pipeline"],
    }
    if provider == "hubspot":
        client_key = env_slug(client_id)
        config.update(
            {
                "auth_mode": "static_token",
                "credential_env": f"HUBSPOT_{client_key}_ACCESS_TOKEN" if client_key else "HUBSPOT_ACCESS_TOKEN",
                "fallback_credential_env": "HUBSPOT_ACCESS_TOKEN",
                "api_version": "2026-03",
                "max_pages": 50,
            }
        )
    return config


def ads_system(provider: str, client_id: str = "") -> dict[str, Any]:
    config: dict[str, Any] = {
        "provider": provider,
        "source_of_truth_for": ["spend", "reach", "impressions", "clicks"],
    }
    if provider == "google_ads":
        client_key = env_slug(client_id)
        config.update(
            {
                "config_env": f"GOOGLE_ADS_{client_key}_CONFIGURATION_FILE" if client_key else "GOOGLE_ADS_CONFIGURATION_FILE",
                "customer_id_env": f"GOOGLE_ADS_{client_key}_CUSTOMER_ID" if client_key else "GOOGLE_ADS_CUSTOMER_ID",
                "login_customer_id_env": f"GOOGLE_ADS_{client_key}_LOGIN_CUSTOMER_ID" if client_key else "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
                "fallback_config_env": "GOOGLE_ADS_CONFIGURATION_FILE",
                "fallback_customer_id_env": "GOOGLE_ADS_CUSTOMER_ID",
                "fallback_login_customer_id_env": "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
            }
        )
    return config


def analytics_system(provider: str, client_id: str = "") -> dict[str, Any]:
    config: dict[str, Any] = {
        "provider": provider,
        "source_of_truth_for": ["sessions", "events", "conversions", "web_revenue"],
    }
    if provider == "google_analytics":
        client_key = env_slug(client_id)
        config.update(
            {
                "auth_mode": "service_account_or_adc",
                "property_id_env": f"GOOGLE_ANALYTICS_{client_key}_PROPERTY_ID" if client_key else "GOOGLE_ANALYTICS_PROPERTY_ID",
                "credentials_file_env": f"GOOGLE_ANALYTICS_{client_key}_CREDENTIALS_FILE" if client_key else "GOOGLE_APPLICATION_CREDENTIALS",
                "fallback_property_id_env": "GOOGLE_ANALYTICS_PROPERTY_ID",
                "fallback_credentials_file_env": "GOOGLE_APPLICATION_CREDENTIALS",
                "limit": 1000,
            }
        )
    return config


def default_systems(
    crm: str = "mock_crm",
    ads: str = "mock_ads",
    client_id: str = "",
    analytics: str | None = None,
) -> dict[str, Any]:
    systems = {
        "crm": crm_system(crm, client_id=client_id),
        "ads": [ads_system(ads, client_id=client_id)],
    }
    if analytics:
        systems["analytics"] = analytics_system(analytics, client_id=client_id)
    return systems


def default_metrics() -> dict[str, Any]:
    return {
        "leads": {
            "canonical_object": "contact",
            "description": "New leads created in the selected period.",
        },
        "pipeline_amount": {
            "canonical_object": "opportunity",
            "description": "Open and won opportunity value in the selected period.",
        },
        "reach": {
            "canonical_object": "metric_snapshot",
            "description": "Unique people reached by paid media where the source platform provides it.",
        },
    }
