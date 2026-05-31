"""Read-only Google Analytics 4 connector for Praxis Reach."""

from __future__ import annotations

from typing import Any, Callable

from .base import ConnectorCheck, ConnectorDiscovery, ConnectorResult, config_or_env_with_fallback, env_value_with_fallback, system_config
from .google_analytics_client import GoogleAnalyticsClient, GoogleAnalyticsClientError
from praxis.reach.conversions import conversion_definitions, conversion_match, describe_conversion_definitions
from praxis.reach.manifests import QueryManifest
from praxis.reach.models import ClientCapsule


GA4_METRIC_MAP = {
    "sessions": "sessions",
    "active_users": "activeUsers",
    "total_users": "totalUsers",
    "event_count": "eventCount",
    "key_events": "keyEvents",
    "conversions": "keyEvents",
    "revenue": "purchaseRevenue",
    "engagement_rate": "engagementRate",
    "conversion_rate": "keyEvents",
}


class GoogleAnalyticsConnector:
    provider = "google_analytics"
    connector_version = "google-analytics-ga4-readonly-v1"

    def __init__(self, client_factory: Callable[..., GoogleAnalyticsClient] = GoogleAnalyticsClient) -> None:
        self.client_factory = client_factory

    def capabilities(self) -> dict[str, Any]:
        return {
            "kind": "analytics",
            "mode": "read_only",
            "auth": "client-specific GA4 property id + service-account or ADC credential reference",
            "objects": ["web_property", "traffic_channel", "landing_page", "metric_snapshot"],
            "metrics": sorted(GA4_METRIC_MAP),
            "supports_deep_links": True,
            "storage_levels": ["metadata", "aggregate_summary"],
            "status": "experimental",
            "live_setup_check": True,
            "query_templates": ["website_performance"],
        }

    def list_resources(self, capsule: ClientCapsule) -> list[str]:
        return ["properties", "reports", "metrics", "dimensions"]

    def introspect_schema(self, capsule: ClientCapsule) -> dict[str, Any]:
        return {
            "metrics": sorted(set(GA4_METRIC_MAP.values())),
            "dimensions": ["sessionDefaultChannelGroup", "landingPagePlusQueryString", "date"],
        }

    def connector_config(self, capsule: ClientCapsule) -> tuple[dict[str, Any], str, str, str, str]:
        config = system_config(capsule, self.provider)
        property_id, property_source, _ = config_or_env_with_fallback(
            config,
            "property_id",
            "property_id_env",
            "fallback_property_id_env",
            "GOOGLE_ANALYTICS_PROPERTY_ID",
        )
        credentials_env, credentials_file = env_value_with_fallback(
            config,
            "credentials_file_env",
            "fallback_credentials_file_env",
            "GOOGLE_APPLICATION_CREDENTIALS",
        )
        return config, property_source, str(property_id), credentials_env, credentials_file

    def check_setup(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorCheck:
        _config, property_source, property_id, credentials_env, credentials_file = self.connector_config(capsule)
        missing = []
        if not property_id:
            missing.append(property_source)
        if self.client_factory is not GoogleAnalyticsClient:
            package_status = "injected"
        else:
            try:
                import google.analytics.data_v1beta  # type: ignore  # noqa: F401
                package_status = "installed"
            except ImportError:
                package_status = "missing"
        warnings = []
        if package_status == "missing":
            warnings.append('Install the optional dependency with `python3 -m pip install "praxis-ktos[google-analytics]"`.')
        if not credentials_file:
            warnings.append(
                f"No {credentials_env} value was found. Live queries may still work if Application Default Credentials are configured."
            )
        details = {
            "package": package_status,
            "property_id_source": property_source,
            "property_id": property_id,
            "credentials_file_env": credentials_env,
            "auth_mode": _auth_mode(capsule),
            "mode": "read_only",
        }
        if missing or package_status == "missing":
            return ConnectorCheck(
                provider=self.provider,
                status="missing_configuration",
                message="Google Analytics connector is not ready.",
                details={**details, "missing": missing},
                warnings=warnings,
            )
        if live:
            try:
                self.client_factory(credentials_file=credentials_file, max_retries=int(_config.get("max_retries") or 3)).run_report(
                    property_id=property_id,
                    metrics=["activeUsers"],
                    dimensions=[],
                    start_date="7daysAgo",
                    end_date="today",
                    limit=1,
                )
            except GoogleAnalyticsClientError as exc:
                return ConnectorCheck(
                    provider=self.provider,
                    status="api_error",
                    message=str(exc),
                    details=details,
                    warnings=warnings,
                )
            return ConnectorCheck(
                provider=self.provider,
                status="ok",
                message="Google Analytics property and Data API access verified.",
                details=details,
                warnings=warnings,
            )
        return ConnectorCheck(
            provider=self.provider,
            status="configured",
            message="Google Analytics local configuration is present. Add --live to verify Data API access.",
            details=details,
            warnings=warnings + ["Static setup checks do not call Google Analytics; they only verify local configuration."],
        )

    def discover_resources(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorDiscovery:
        _config, property_source, property_id, credentials_env, credentials_file = self.connector_config(capsule)
        details = {
            "property_id_source": property_source,
            "configured_property_id": property_id,
            "credentials_file_env": credentials_env,
            "auth_mode": _auth_mode(capsule),
        }
        resources = []
        if property_id:
            resources.append({"kind": "configured_property", "id": property_id.replace("properties/", ""), "resource_name": _property_resource(property_id)})
        if not live:
            return ConnectorDiscovery(
                provider=self.provider,
                status="configured" if property_id else "missing_configuration",
                message="Static discovery shows configured GA4 property references. Add --live to query account summaries.",
                resources=resources,
                details=details,
                warnings=[] if property_id else [f"Set {property_source} before running live discovery."],
            )
        try:
            discovered = self.client_factory(credentials_file=credentials_file, max_retries=int(_config.get("max_retries") or 3)).list_account_summaries()
        except GoogleAnalyticsClientError as exc:
            return ConnectorDiscovery(
                provider=self.provider,
                status="api_error",
                message=str(exc),
                resources=resources,
                details=details,
            )
        resources.extend(discovered)
        warnings = []
        if property_id:
            configured_id = property_id.replace("properties/", "")
            property_ids = {str(item.get("id")) for item in discovered if item.get("kind") == "property"}
            if property_ids and configured_id not in property_ids:
                warnings.append("Configured GA4 property was not returned by account-summary discovery. Verify property id and permissions.")
        return ConnectorDiscovery(
            provider=self.provider,
            status="ok",
            message="Google Analytics discovery completed.",
            resources=resources,
            details={**details, "resource_count": len(resources)},
            warnings=warnings,
        )

    def run_query(self, capsule: ClientCapsule, manifest: QueryManifest, params: dict[str, Any]) -> ConnectorResult:
        config, property_source, property_id, credentials_env, credentials_file = self.connector_config(capsule)
        if not property_id:
            raise RuntimeError(f"Google Analytics connector requires {property_source}.")
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        if not start_date or not end_date:
            raise RuntimeError("Google Analytics connector requires start_date and end_date query params.")
        api_metrics = _api_metrics_for_manifest(manifest)
        if not api_metrics:
            return ConnectorResult(
                provider=self.provider,
                summary=f"Google Analytics had no requested metrics for manifest {manifest.manifest_id}.",
                metrics={},
                source_links=[_property_link(property_id)],
                warnings=["Manifest does not request any GA4-backed metric outputs."],
                row_count=0,
                metadata={"connector_version": self.connector_version, "property_id_source": property_source},
            )
        client = self.client_factory(credentials_file=credentials_file, max_retries=int(config.get("max_retries") or 3))
        try:
            report = client.run_report(
                property_id=property_id,
                metrics=api_metrics,
                dimensions=[str(item) for item in config.get("dimensions", [])],
                start_date=str(start_date),
                end_date=str(end_date),
                limit=int(config.get("limit") or 1000),
            )
        except GoogleAnalyticsClientError as exc:
            raise RuntimeError(str(exc)) from exc
        metrics = _aggregate_ga4_metrics(report.rows)
        definitions = conversion_definitions(capsule, self.provider)
        conversion_metadata: dict[str, Any] = {}
        conversion_report = None
        if definitions and any(output in manifest.outputs for output in ("conversions", "key_events", "event_count", "conversion_rate")):
            try:
                conversion_report = client.run_report(
                    property_id=property_id,
                    metrics=["eventCount", "keyEvents"],
                    dimensions=["eventName"],
                    start_date=str(start_date),
                    end_date=str(end_date),
                    limit=int(config.get("conversion_limit") or 1000),
                )
            except GoogleAnalyticsClientError as exc:
                raise RuntimeError(str(exc)) from exc
            conversion_metrics, conversion_metadata = _aggregate_mapped_ga4_conversions(conversion_report.rows, definitions, sessions=float(metrics.get("sessions") or 0))
            metrics.update(conversion_metrics)
        warnings = [
            "Google Analytics metrics are aggregate summaries; Praxis does not store raw user-level analytics rows.",
            "Confirm GA4 key-event and revenue definitions before treating analytics conversions as canonical.",
        ]
        if definitions:
            warnings.append("Google Analytics conversions were filtered through client conversion definitions.")
        else:
            warnings.append("No client conversion definitions found; GA4 conversion metrics use all reported key events.")
        metadata = dict(report.metadata or {})
        warnings.extend(_quota_warnings(metadata))
        partial_data = report.row_count > len(report.rows)
        if conversion_report is not None and conversion_report.row_count > len(conversion_report.rows):
            partial_data = True
        if partial_data:
            warnings.append("Google Analytics row_count is larger than returned rows; metrics may be partial due to query limit.")
        metadata.update(
            {
                "connector_version": self.connector_version,
                "params": params,
                "property_id_source": property_source,
                "credentials_file_env": credentials_env,
                "auth_mode": _auth_mode(capsule),
                "row_storage": "none",
                "partial_data": partial_data,
                "completeness": "partial" if partial_data else "complete",
                "api_metrics": api_metrics,
                "freshness": {
                    "queried_start_date": str(start_date),
                    "queried_end_date": str(end_date),
                    "source_timezone": "property_default",
                },
                "conversion_definitions": describe_conversion_definitions(definitions),
                "conversion_mapping": conversion_metadata,
            }
        )
        return ConnectorResult(
            provider=self.provider,
            summary=f"Google Analytics scanned {report.row_count} aggregate GA4 report rows for property {property_id} from {start_date} to {end_date}.",
            metrics={key: value for key, value in metrics.items() if key in manifest.outputs},
            source_links=[_property_link(property_id)],
            warnings=warnings,
            row_count=report.row_count,
            metadata=metadata,
        )


def _api_metrics_for_manifest(manifest: QueryManifest) -> list[str]:
    seen: set[str] = set()
    api_metrics: list[str] = []
    outputs = set(manifest.outputs)
    if "conversion_rate" in outputs:
        outputs.add("sessions")
    for output in manifest.outputs:
        api_name = GA4_METRIC_MAP.get(output)
        if api_name and api_name not in seen:
            seen.add(api_name)
            api_metrics.append(api_name)
    if "sessions" in outputs and "sessions" not in seen:
        api_metrics.append("sessions")
    return api_metrics


def _aggregate_ga4_metrics(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    totals = {api_name: 0.0 for api_name in set(GA4_METRIC_MAP.values())}
    engagement_weighted_sum = 0.0
    engagement_weight = 0.0
    for row in rows:
        metrics = row.get("metrics") if isinstance(row, dict) else None
        if not isinstance(metrics, dict):
            continue
        for api_name in totals:
            totals[api_name] += _number(metrics.get(api_name))
        sessions_for_row = _number(metrics.get("sessions"))
        if "engagementRate" in metrics and sessions_for_row > 0:
            engagement_weighted_sum += _number(metrics.get("engagementRate")) * sessions_for_row
            engagement_weight += sessions_for_row
    sessions = totals.get("sessions", 0.0)
    event_count = totals.get("eventCount", 0.0)
    key_events = totals.get("keyEvents", 0.0)
    metrics = {
        "sessions": _int_if_whole(totals.get("sessions", 0.0)),
        "active_users": _int_if_whole(totals.get("activeUsers", 0.0)),
        "total_users": _int_if_whole(totals.get("totalUsers", 0.0)),
        "event_count": _int_if_whole(event_count),
        "key_events": _int_if_whole(key_events),
        "conversions": _int_if_whole(key_events),
        "revenue": round(totals.get("purchaseRevenue", 0.0), 2),
        "engagement_rate": round(engagement_weighted_sum / engagement_weight, 4) if engagement_weight else 0,
        "conversion_rate": round(key_events / sessions, 4) if sessions else 0,
    }
    return metrics


def _aggregate_mapped_ga4_conversions(
    rows: list[dict[str, Any]],
    definitions: list[dict[str, Any]],
    *,
    sessions: float,
) -> tuple[dict[str, float | int], dict[str, Any]]:
    event_count = 0.0
    key_events = 0.0
    matched: dict[str, dict[str, Any]] = {}
    ignored = 0
    for row in rows:
        dimensions = row.get("dimensions") if isinstance(row, dict) else None
        metrics = row.get("metrics") if isinstance(row, dict) else None
        if not isinstance(dimensions, dict) or not isinstance(metrics, dict):
            continue
        event_name = str(dimensions.get("eventName") or "")
        definition = conversion_match(event_name, definitions)
        if definition is None:
            ignored += 1
            continue
        weight = float(definition.get("weight") or 1.0)
        row_events = _number(metrics.get("eventCount")) * weight
        row_key_events = _number(metrics.get("keyEvents")) * weight
        event_count += row_events
        key_events += row_key_events
        key = str(definition.get("id") or definition.get("source_name") or event_name)
        bucket = matched.setdefault(key, {"rows": 0, "event_count": 0.0, "key_events": 0.0})
        bucket["rows"] += 1
        bucket["event_count"] += row_events
        bucket["key_events"] += row_key_events
    return (
        {
            "event_count": _int_if_whole(event_count),
            "key_events": _int_if_whole(key_events),
            "conversions": _int_if_whole(key_events),
            "conversion_rate": round(key_events / sessions, 4) if sessions else 0,
        },
        {"matched": matched, "ignored_rows": ignored, "definition_count": len(definitions)},
    )


def _quota_warnings(metadata: dict[str, Any]) -> list[str]:
    quota = metadata.get("property_quota") or metadata.get("quota")
    if not isinstance(quota, dict) or not quota:
        return []
    warnings: list[str] = []
    text = str(quota)
    for key in ("tokens_per_day", "tokensPerDay", "tokens_per_hour", "tokensPerHour", "concurrent_requests", "concurrentRequests"):
        value = quota.get(key)
        remaining = _remaining_quota(value)
        if remaining is not None and remaining <= 10:
            warnings.append(f"GA4 quota is low for {key}: {remaining} remaining.")
    if "potentiallyThresholdedRequestsPerHour" in text or "potentially_thresholded_requests_per_hour" in text:
        warnings.append("GA4 quota metadata includes thresholding counters; interpret small audience reports carefully.")
    return warnings


def _remaining_quota(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("remaining") or value.get("remaining_tokens") or value.get("remainingTokens")
    if hasattr(value, "remaining"):
        value = getattr(value, "remaining")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_if_whole(value: float) -> float | int:
    return int(value) if float(value).is_integer() else round(float(value), 4)


def _property_link(property_id: str) -> str:
    property_key = str(property_id).replace("properties/", "")
    return f"https://analytics.google.com/analytics/web/#/p{property_key}/reports"


def _property_resource(property_id: str) -> str:
    return str(property_id) if str(property_id).startswith("properties/") else f"properties/{property_id}"


def _auth_mode(capsule: ClientCapsule) -> str:
    config = system_config(capsule, GoogleAnalyticsConnector.provider)
    return str(config.get("auth_mode") or "service_account_or_adc")
