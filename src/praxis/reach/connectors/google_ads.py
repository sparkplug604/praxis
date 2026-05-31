"""Read-only Google Ads connector for Praxis Reach."""

from __future__ import annotations

from typing import Any, Callable

from .base import ConnectorCheck, ConnectorDiscovery, ConnectorResult, config_or_env_with_fallback, env_value_with_fallback, system_config
from .google_ads_client import GoogleAdsClient, GoogleAdsClientError, clean_customer_id
from praxis.reach.conversions import conversion_definitions, conversion_match, describe_conversion_definitions
from praxis.reach.manifests import QueryManifest
from praxis.reach.models import ClientCapsule


class GoogleAdsConnector:
    provider = "google_ads"
    connector_version = "google-ads-readonly-v1"

    def __init__(self, client_factory: Callable[..., GoogleAdsClient] = GoogleAdsClient) -> None:
        self.client_factory = client_factory

    def capabilities(self) -> dict[str, Any]:
        return {
            "kind": "ads",
            "mode": "read_only",
            "auth": "client-specific google-ads.yaml reference + customer id",
            "objects": ["campaign", "ad_group", "ad", "metric_snapshot"],
            "metrics": ["spend", "impressions", "clicks", "ctr", "cpc", "cpm", "conversions", "conversion_value", "conversion_rate"],
            "supports_deep_links": False,
            "storage_levels": ["metadata", "aggregate_summary"],
            "status": "experimental",
            "live_setup_check": True,
            "query_templates": ["campaign_performance", "conversion_action_performance"],
        }

    def list_resources(self, capsule: ClientCapsule) -> list[str]:
        return ["campaigns", "ad_groups", "ads", "metrics"]

    def introspect_schema(self, capsule: ClientCapsule) -> dict[str, Any]:
        return {
            "campaigns": ["campaign.id", "campaign.name", "campaign.status"],
            "metrics": [
                "metrics.cost_micros",
                "metrics.impressions",
                "metrics.clicks",
                "metrics.ctr",
                "metrics.conversions",
                "metrics.conversions_value",
            ],
        }

    def connector_config(self, capsule: ClientCapsule) -> tuple[dict[str, Any], str, str, str, str, str, str]:
        config = system_config(capsule, self.provider)
        config_env, config_path = env_value_with_fallback(config, "config_env", "fallback_config_env", "GOOGLE_ADS_CONFIGURATION_FILE")
        customer_id, customer_source, _ = config_or_env_with_fallback(
            config,
            "customer_id",
            "customer_id_env",
            "fallback_customer_id_env",
            "GOOGLE_ADS_CUSTOMER_ID",
        )
        login_customer_id, login_source, _ = config_or_env_with_fallback(
            config,
            "login_customer_id",
            "login_customer_id_env",
            "fallback_login_customer_id_env",
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
        )
        return config, config_env, config_path, customer_source, clean_customer_id(customer_id), login_source, clean_customer_id(login_customer_id)

    def check_setup(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorCheck:
        _config, config_env, config_path, customer_source, customer_id, login_source, login_customer_id = self.connector_config(capsule)
        missing = []
        if not config_path:
            missing.append(config_env)
        if not customer_id:
            missing.append(customer_source)
        if self.client_factory is not GoogleAdsClient:
            package_status = "injected"
        else:
            try:
                import google.ads.googleads.client  # type: ignore  # noqa: F401
                package_status = "installed"
            except ImportError:
                package_status = "missing"
        if missing or package_status == "missing":
            warnings = []
            if package_status == "missing":
                warnings.append('Install the optional dependency with `python3 -m pip install "praxis-ktos[google-ads]"`.')
            return ConnectorCheck(
                provider=self.provider,
                status="missing_configuration",
                message="Google Ads connector is not ready.",
                details={
                    "missing": missing,
                    "package": package_status,
                    "config_env": config_env,
                    "customer_id_source": customer_source,
                    "login_customer_id_source": login_source if login_customer_id else "",
                },
                warnings=warnings,
            )
        details = {
            "package": package_status,
            "config_env": config_env,
            "customer_id_source": customer_source,
            "customer_id": customer_id,
            "login_customer_id_source": login_source if login_customer_id else "",
            "mode": "read_only",
        }
        if live:
            try:
                accessible = self.client_factory(
                    configuration_file=config_path,
                    login_customer_id=login_customer_id,
                    max_retries=int(_config.get("max_retries") or 3),
                ).list_accessible_customers()
            except GoogleAdsClientError as exc:
                return ConnectorCheck(
                    provider=self.provider,
                    status="api_error",
                    message=str(exc),
                    details=details,
                )
            details["accessible_customers_sample"] = accessible[:10]
            configured_resource = f"customers/{customer_id}"
            warnings = []
            manager_children = []
            if login_customer_id:
                try:
                    manager_children = self.client_factory(
                        configuration_file=config_path,
                        login_customer_id=login_customer_id,
                        max_retries=int(_config.get("max_retries") or 3),
                    ).list_customer_clients(login_customer_id)
                except GoogleAdsClientError as exc:
                    warnings.append(f"Manager-account traversal failed for {login_customer_id}: {exc}")
                details["manager_customer_id"] = login_customer_id
                details["manager_children_sample"] = manager_children[:10]
            if accessible and configured_resource not in accessible:
                child_ids = {str(item.get("id")) for item in manager_children}
                if customer_id in child_ids:
                    warnings.append(
                        "Configured customer was found under the manager account, but not in direct accessible customers. "
                        "Praxis will use login_customer_id for report calls."
                    )
                else:
                    warnings.append(
                        "Google Ads API responded, but the configured customer was not returned by accessible-customer "
                        "or manager-child discovery. Verify the customer id before running reports."
                    )
            return ConnectorCheck(
                provider=self.provider,
                status="ok",
                message="Google Ads credentials and accessible-customer API access verified.",
                details=details,
                warnings=warnings,
            )
        return ConnectorCheck(
            provider=self.provider,
            status="configured",
            message="Google Ads local configuration is present. Add --live to verify API access.",
            details=details,
            warnings=["Static setup checks do not call Google Ads; they only verify local configuration."],
        )

    def discover_resources(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorDiscovery:
        _config, config_env, config_path, customer_source, customer_id, login_source, login_customer_id = self.connector_config(capsule)
        details = {
            "config_env": config_env,
            "customer_id_source": customer_source,
            "configured_customer_id": customer_id,
            "login_customer_id_source": login_source if login_customer_id else "",
            "login_customer_id": login_customer_id,
        }
        resources: list[dict[str, Any]] = []
        if customer_id:
            resources.append({"kind": "configured_customer", "id": customer_id, "resource_name": f"customers/{customer_id}"})
        if login_customer_id:
            resources.append({"kind": "configured_manager", "id": login_customer_id, "resource_name": f"customers/{login_customer_id}"})
        if not live:
            return ConnectorDiscovery(
                provider=self.provider,
                status="configured" if customer_id else "missing_configuration",
                message="Static discovery shows configured Google Ads customer references. Add --live to query accessible accounts.",
                resources=resources,
                details=details,
                warnings=[] if customer_id else [f"Set {customer_source} before running live discovery."],
            )
        if not config_path:
            return ConnectorDiscovery(
                provider=self.provider,
                status="missing_configuration",
                message=f"Google Ads live discovery requires {config_env}.",
                resources=resources,
                details=details,
            )
        try:
            client = self.client_factory(
                configuration_file=config_path,
                login_customer_id=login_customer_id,
                max_retries=int(_config.get("max_retries") or 3),
            )
            accessible = client.list_accessible_customers()
            for resource_name in accessible:
                resources.append({"kind": "accessible_customer", "id": clean_customer_id(resource_name), "resource_name": resource_name})
            if login_customer_id:
                for child in client.list_customer_clients(login_customer_id):
                    resources.append({"kind": "manager_child", **child})
        except GoogleAdsClientError as exc:
            return ConnectorDiscovery(
                provider=self.provider,
                status="api_error",
                message=str(exc),
                resources=resources,
                details=details,
            )
        return ConnectorDiscovery(
            provider=self.provider,
            status="ok",
            message="Google Ads discovery completed.",
            resources=resources,
            details={**details, "resource_count": len(resources)},
        )

    def run_query(self, capsule: ClientCapsule, manifest: QueryManifest, params: dict[str, Any]) -> ConnectorResult:
        config, config_env, config_path, customer_source, customer_id, login_source, login_customer_id = self.connector_config(capsule)
        if not config_path or not customer_id:
            raise RuntimeError(f"Google Ads connector requires {config_env} and {customer_source}.")

        start_date = params.get("start_date")
        end_date = params.get("end_date")
        if not start_date or not end_date:
            raise RuntimeError("Google Ads connector requires start_date and end_date query params.")
        max_batches = int(config.get("max_batches") or 100)
        query = campaign_performance_query(str(start_date), str(end_date), limit=int(config.get("limit") or 10000))
        client = self.client_factory(
            configuration_file=config_path,
            login_customer_id=login_customer_id,
            max_retries=int(config.get("max_retries") or 3),
        )
        try:
            report = client.search_stream(customer_id=customer_id, query=query, max_batches=max_batches)
        except GoogleAdsClientError as exc:
            raise RuntimeError(str(exc)) from exc

        definitions = conversion_definitions(capsule, self.provider)
        conversion_report = None
        if definitions and any(output in manifest.outputs for output in ("conversions", "conversion_value", "conversion_rate")):
            try:
                conversion_report = client.search_stream(
                    customer_id=customer_id,
                    query=conversion_action_performance_query(str(start_date), str(end_date), limit=int(config.get("conversion_limit") or 10000)),
                    max_batches=max_batches,
                )
            except GoogleAdsClientError as exc:
                raise RuntimeError(str(exc)) from exc

        metrics = _aggregate_campaign_metrics(report.rows)
        conversion_metadata: dict[str, Any] = {}
        if conversion_report is not None:
            conversion_metrics, conversion_metadata = _aggregate_mapped_conversions(conversion_report.rows, definitions)
            metrics.update({key: value for key, value in conversion_metrics.items() if key in {"conversions", "conversion_value", "conversion_rate"}})
            clicks = float(metrics.get("clicks") or 0)
            metrics["conversion_rate"] = round(float(metrics.get("conversions") or 0) / clicks, 4) if clicks else 0
        warnings = [
            "Google Ads metrics are aggregate summaries; Praxis does not store raw campaign rows.",
            "Treat ad-platform conversions as directional until reconciled against CRM-confirmed revenue.",
        ]
        if definitions:
            warnings.append("Google Ads conversions were filtered through client conversion definitions.")
        else:
            warnings.append("No client conversion definitions found; Google Ads conversion metrics include all platform-reported conversions.")
        partial_data = report.truncated or bool(conversion_report and conversion_report.truncated)
        if partial_data:
            warnings.append(f"Google Ads stream reached max_batches={max_batches}; returned metrics may be partial.")
        row_count = len(report.rows) + (len(conversion_report.rows) if conversion_report else 0)
        return ConnectorResult(
            provider=self.provider,
            summary=f"Google Ads scanned {row_count} aggregate metric rows for customer {customer_id} from {start_date} to {end_date}.",
            metrics={key: value for key, value in metrics.items() if key in manifest.outputs},
            source_links=[f"https://ads.google.com/aw/overview?ocid={customer_id}"],
            warnings=warnings,
            row_count=row_count,
            metadata={
                "connector_version": self.connector_version,
                "params": params,
                "config_env": config_env,
                "customer_id_source": customer_source,
                "login_customer_id_source": login_source if login_customer_id else "",
                "manager_customer_id": login_customer_id,
                "row_storage": "none",
                "partial_data": partial_data,
                "completeness": "partial" if partial_data else "complete",
                "query_template": "campaign_performance",
                "batches_read": report.batches_read,
                "max_batches": max_batches,
                "conversion_definitions": describe_conversion_definitions(definitions),
                "conversion_mapping": conversion_metadata,
            },
        )


def campaign_performance_query(start_date: str, end_date: str, *, limit: int = 10000) -> str:
    return f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          metrics.cost_micros,
          metrics.impressions,
          metrics.clicks,
          metrics.conversions,
          metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        LIMIT {max(1, int(limit))}
    """


def conversion_action_performance_query(start_date: str, end_date: str, *, limit: int = 10000) -> str:
    return f"""
        SELECT
          segments.conversion_action,
          segments.conversion_action_name,
          metrics.conversions,
          metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        LIMIT {max(1, int(limit))}
    """


def _aggregate_campaign_metrics(rows: list[Any]) -> dict[str, float | int]:
    spend_micros = 0
    impressions = 0
    clicks = 0
    conversions = 0.0
    conversion_value = 0.0
    for row in rows:
        spend_micros += int(_metric(row, "cost_micros") or 0)
        impressions += int(_metric(row, "impressions") or 0)
        clicks += int(_metric(row, "clicks") or 0)
        conversions += float(_metric(row, "conversions") or 0)
        conversion_value += float(_metric(row, "conversions_value") or 0)
    spend = round(spend_micros / 1_000_000, 2)
    return {
        "spend": spend,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": round(clicks / impressions, 4) if impressions else 0,
        "cpc": round(spend / clicks, 2) if clicks else 0,
        "cpm": round((spend / impressions) * 1000, 2) if impressions else 0,
        "conversions": round(conversions, 4),
        "conversion_value": round(conversion_value, 2),
        "conversion_rate": round(conversions / clicks, 4) if clicks else 0,
    }


def _aggregate_mapped_conversions(rows: list[Any], definitions: list[dict[str, Any]]) -> tuple[dict[str, float | int], dict[str, Any]]:
    conversions = 0.0
    conversion_value = 0.0
    matched: dict[str, dict[str, Any]] = {}
    ignored = 0
    for row in rows:
        action_id = _segment(row, "conversion_action")
        action_name = _segment(row, "conversion_action_name")
        definition = conversion_match(action_id, definitions) or conversion_match(action_name, definitions)
        if definition is None:
            ignored += 1
            continue
        weight = float(definition.get("weight") or 1.0)
        row_conversions = float(_metric(row, "conversions") or 0) * weight
        row_value = float(_metric(row, "conversions_value") or 0) * weight
        conversions += row_conversions
        conversion_value += row_value
        key = str(definition.get("id") or definition.get("source_name") or action_name or action_id)
        bucket = matched.setdefault(key, {"rows": 0, "conversions": 0.0, "conversion_value": 0.0})
        bucket["rows"] += 1
        bucket["conversions"] += row_conversions
        bucket["conversion_value"] += row_value
    return (
        {
            "conversions": round(conversions, 4),
            "conversion_value": round(conversion_value, 2),
        },
        {"matched": matched, "ignored_rows": ignored, "definition_count": len(definitions)},
    )


def _metric(row: Any, name: str) -> Any:
    if isinstance(row, dict):
        metrics = row.get("metrics")
        if isinstance(metrics, dict):
            return metrics.get(name)
        return row.get(name)
    metrics = getattr(row, "metrics", None)
    if metrics is None:
        return None
    return getattr(metrics, name, None)


def _segment(row: Any, name: str) -> str:
    if isinstance(row, dict):
        segments = row.get("segments")
        if isinstance(segments, dict):
            return str(segments.get(name) or "")
        return str(row.get(name) or "")
    segments = getattr(row, "segments", None)
    if segments is None:
        return ""
    return str(getattr(segments, name, "") or "")
