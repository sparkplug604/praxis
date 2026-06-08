"""Read-only BigQuery warehouse connector for Praxis Reach."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Callable

from .base import ConnectorCheck, ConnectorDiscovery, ConnectorResult, config_or_env_with_fallback, env_value_with_fallback, system_config
from .bigquery_client import BigQueryClient, BigQueryClientError
from praxis.reach.manifests import QueryManifest
from praxis.reach.models import ClientCapsule


_PROJECT_RE = re.compile(r"^[A-Za-z0-9_\-:.]+$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class BigQueryConnector:
    provider = "bigquery"
    connector_version = "bigquery-readonly-v1"

    def __init__(self, client_factory: Callable[..., BigQueryClient] = BigQueryClient) -> None:
        self.client_factory = client_factory

    def capabilities(self) -> dict[str, Any]:
        return {
            "kind": "warehouse",
            "mode": "read_only",
            "auth": "client-specific BigQuery project/dataset + service-account or ADC credential reference",
            "objects": ["contact", "company", "opportunity", "campaign", "buyer_signal", "segment", "metric_snapshot"],
            "metrics": [
                "contacts",
                "accounts",
                "segment_size",
                "suppressed_count",
                "missing_email_count",
                "stale_record_count",
                "buyer_signal_count",
                "avg_signal_strength",
                "leads",
                "opportunities",
                "pipeline_amount",
                "closed_won_revenue",
                "conversion_rate",
            ],
            "supports_deep_links": False,
            "storage_levels": ["pointer", "metadata", "aggregate_summary", "redacted_sample"],
            "status": "experimental",
            "live_setup_check": True,
            "query_templates": [
                "warehouse_segment_size_preview",
                "warehouse_buyer_signal_rollup",
                "warehouse_suppression_check",
                "warehouse_campaign_outcome_rollup",
            ],
        }

    def list_resources(self, capsule: ClientCapsule) -> list[str]:
        return ["datasets", "tables", "columns", "aggregate_queries"]

    def introspect_schema(self, capsule: ClientCapsule) -> dict[str, Any]:
        config, _project_source, project_id, _dataset_source, dataset, _credentials_env, _credentials_file = self.connector_config(capsule)
        return {
            "project_id": project_id,
            "dataset": dataset,
            "allowed_tables": _allowed_tables(config),
            "configured_tables": _configured_tables(config),
        }

    def connector_config(self, capsule: ClientCapsule) -> tuple[dict[str, Any], str, str, str, str, str, str]:
        config = system_config(capsule, self.provider)
        project_id, project_source, _ = config_or_env_with_fallback(
            config,
            "project_id",
            "project_id_env",
            "fallback_project_id_env",
            "BIGQUERY_PROJECT_ID",
        )
        dataset, dataset_source, _ = config_or_env_with_fallback(
            config,
            "dataset",
            "dataset_env",
            "fallback_dataset_env",
            "BIGQUERY_DATASET",
        )
        credentials_env, credentials_file = env_value_with_fallback(
            config,
            "credentials_file_env",
            "fallback_credentials_file_env",
            "GOOGLE_APPLICATION_CREDENTIALS",
        )
        return config, project_source, str(project_id), dataset_source, str(dataset), credentials_env, credentials_file

    def check_setup(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorCheck:
        config, project_source, project_id, dataset_source, dataset, credentials_env, credentials_file = self.connector_config(capsule)
        missing = []
        if not project_id:
            missing.append(project_source)
        if not dataset:
            missing.append(dataset_source)
        if self.client_factory is not BigQueryClient:
            package_status = "injected"
        else:
            try:
                import google.cloud.bigquery  # type: ignore  # noqa: F401
                package_status = "installed"
            except ImportError:
                package_status = "missing"
        warnings = []
        if package_status == "missing":
            warnings.append('Install the optional dependency with `python3 -m pip install "praxis-ktos[bigquery]"`.')
        if not credentials_file:
            warnings.append(
                f"No {credentials_env} value was found. Live queries may still work if Application Default Credentials are configured."
            )
        details = {
            "package": package_status,
            "project_id_source": project_source,
            "project_id": project_id,
            "dataset_source": dataset_source,
            "dataset": dataset,
            "credentials_file_env": credentials_env,
            "location": str(config.get("location") or ""),
            "mode": "read_only",
            "max_bytes_billed": int(config.get("max_bytes_billed") or 0),
        }
        if missing or package_status == "missing":
            return ConnectorCheck(
                provider=self.provider,
                status="missing_configuration",
                message="BigQuery connector is not ready.",
                details={**details, "missing": missing},
                warnings=warnings,
            )
        if live:
            try:
                client = self.client_factory(
                    project_id=project_id,
                    credentials_file=credentials_file,
                    location=str(config.get("location") or ""),
                    max_retries=int(config.get("max_retries") or 3),
                )
                dry_run = client.dry_run("SELECT 1", maximum_bytes_billed=int(config.get("max_bytes_billed") or 0), labels=_job_labels(capsule, "setup_check"))
            except BigQueryClientError as exc:
                return ConnectorCheck(provider=self.provider, status="api_error", message=str(exc), details=details, warnings=warnings)
            return ConnectorCheck(
                provider=self.provider,
                status="ok",
                message="BigQuery credentials and dry-run query access verified.",
                details={**details, "dry_run": dry_run},
                warnings=warnings,
            )
        return ConnectorCheck(
            provider=self.provider,
            status="configured",
            message="BigQuery local configuration is present. Add --live to verify API access.",
            details=details,
            warnings=warnings + ["Static setup checks do not call BigQuery; they only verify local configuration."],
        )

    def discover_resources(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorDiscovery:
        config, project_source, project_id, dataset_source, dataset, credentials_env, credentials_file = self.connector_config(capsule)
        details = {
            "project_id_source": project_source,
            "configured_project_id": project_id,
            "dataset_source": dataset_source,
            "configured_dataset": dataset,
            "credentials_file_env": credentials_env,
            "allowed_tables": _allowed_tables(config),
        }
        resources = [
            {"kind": "configured_dataset", "id": dataset, "resource_name": f"{project_id}.{dataset}"}
        ] if project_id and dataset else []
        if not live:
            return ConnectorDiscovery(
                provider=self.provider,
                status="configured" if project_id and dataset else "missing_configuration",
                message="Static discovery shows configured BigQuery dataset and allowed tables. Add --live to list tables.",
                resources=resources,
                details=details,
                warnings=[] if project_id and dataset else ["Set BigQuery project_id and dataset before running live discovery."],
            )
        try:
            client = self.client_factory(
                project_id=project_id,
                credentials_file=credentials_file,
                location=str(config.get("location") or ""),
                max_retries=int(config.get("max_retries") or 3),
            )
            resources.extend(
                client.list_tables(
                    project_id=project_id,
                    dataset=dataset,
                    include_columns=bool(config.get("discover_columns")),
                )
            )
        except BigQueryClientError as exc:
            return ConnectorDiscovery(provider=self.provider, status="api_error", message=str(exc), resources=resources, details=details)
        return ConnectorDiscovery(
            provider=self.provider,
            status="ok",
            message="BigQuery discovery completed.",
            resources=resources,
            details={**details, "resource_count": len(resources)},
        )

    def run_query(self, capsule: ClientCapsule, manifest: QueryManifest, params: dict[str, Any]) -> ConnectorResult:
        config, project_source, project_id, dataset_source, dataset, credentials_env, credentials_file = self.connector_config(capsule)
        if not project_id or not dataset:
            raise RuntimeError(f"BigQuery connector requires {project_source} and {dataset_source}.")
        plan = _query_plan(config, manifest, params, project_id=project_id, dataset=dataset)
        max_bytes_billed = int(config.get("max_bytes_billed") or 0)
        client = self.client_factory(
            project_id=project_id,
            credentials_file=credentials_file,
            location=str(config.get("location") or ""),
            max_retries=int(config.get("max_retries") or 3),
        )
        labels = _job_labels(capsule, manifest.manifest_id)
        try:
            dry_run = client.dry_run(
                plan["query"],
                parameters=plan["parameters"],
                maximum_bytes_billed=max_bytes_billed or None,
                labels=labels,
            )
        except BigQueryClientError as exc:
            raise RuntimeError(str(exc)) from exc
        estimated_bytes = int(dry_run.get("total_bytes_processed") or 0)
        if max_bytes_billed and estimated_bytes > max_bytes_billed:
            raise RuntimeError(
                f"BigQuery dry run estimated {estimated_bytes} bytes, above max_bytes_billed={max_bytes_billed}. "
                "Narrow the manifest or raise the client capsule limit intentionally."
            )
        try:
            result = client.query(
                plan["query"],
                parameters=plan["parameters"],
                maximum_bytes_billed=max_bytes_billed or None,
                labels=labels,
            )
        except BigQueryClientError as exc:
            raise RuntimeError(str(exc)) from exc
        row = dict(result.rows[0]) if result.rows else {}
        metrics = _metrics_from_row(row, manifest.outputs)
        warnings = [
            "BigQuery connector stores aggregate evidence by default; Praxis does not copy raw warehouse rows for this manifest.",
            *plan["warnings"],
        ]
        metadata = dict(result.metadata or {})
        metadata.update(
            {
                "connector_version": self.connector_version,
                "params": params,
                "project_id": project_id,
                "dataset": dataset,
                "credentials_file_env": credentials_env,
                "location": str(config.get("location") or ""),
                "row_storage": "none" if manifest.pii_policy == "none" else "redacted_sample",
                "dry_run_bytes_estimate": estimated_bytes,
                "dry_run_job_id": dry_run.get("job_id", ""),
                "max_bytes_billed": max_bytes_billed,
                "tables_referenced": plan["tables_referenced"],
                "query_template": plan["query_template"],
                "query_parameters": sorted(plan["parameters"]),
            }
        )
        return ConnectorResult(
            provider=self.provider,
            summary=_summary_for_manifest(manifest, metrics, plan["tables_referenced"]),
            metrics=metrics,
            source_links=[f"bigquery://{table}" for table in plan["tables_referenced"]],
            warnings=warnings,
            row_count=int(result.row_count or len(result.rows)),
            storage_level=manifest.storage_level,
            metadata=metadata,
        )


def _query_plan(config: dict[str, Any], manifest: QueryManifest, params: dict[str, Any], *, project_id: str, dataset: str) -> dict[str, Any]:
    if manifest.manifest_id in {"warehouse_segment_size_preview", "warehouse_suppression_check"}:
        return _contacts_query_plan(config, manifest, project_id=project_id, dataset=dataset)
    if manifest.manifest_id == "warehouse_buyer_signal_rollup":
        return _buyer_signal_query_plan(config, manifest, params, project_id=project_id, dataset=dataset)
    if manifest.manifest_id == "warehouse_campaign_outcome_rollup":
        return _campaign_outcome_query_plan(config, manifest, params, project_id=project_id, dataset=dataset)
    raise RuntimeError(f"BigQuery connector does not support manifest {manifest.manifest_id}.")


def _contacts_query_plan(config: dict[str, Any], manifest: QueryManifest, *, project_id: str, dataset: str) -> dict[str, Any]:
    table, table_name = _configured_table(config, "contacts_table", "contacts", project_id=project_id, dataset=dataset)
    warnings = []
    expressions = ["COUNT(*) AS contacts"]
    if "segment_size" in manifest.outputs:
        expressions.append("COUNT(*) AS segment_size")
    account_column = _optional_column(config, "account_id_column", "account_id")
    if account_column and "accounts" in manifest.outputs:
        expressions.append(f"COUNT(DISTINCT `{account_column}`) AS accounts")
    email_column = _optional_column(config, "email_column", "email")
    if email_column and "missing_email_count" in manifest.outputs:
        expressions.append(f"SUM(CASE WHEN `{email_column}` IS NULL OR CAST(`{email_column}` AS STRING) = '' THEN 1 ELSE 0 END) AS missing_email_count")
    suppression_column = _optional_column(config, "suppression_column", "email_status")
    if suppression_column and "suppressed_count" in manifest.outputs:
        suppressed_values = config.get("suppressed_values") or ["unsubscribed", "bounced", "suppressed", "do_not_contact"]
        values = ", ".join(_sql_string(str(value).lower()) for value in suppressed_values)
        expressions.append(f"SUM(CASE WHEN LOWER(CAST(`{suppression_column}` AS STRING)) IN ({values}) THEN 1 ELSE 0 END) AS suppressed_count")
    updated_at_column = _optional_column(config, "updated_at_column", "")
    parameters: dict[str, Any] = {}
    if updated_at_column and "stale_record_count" in manifest.outputs:
        stale_days = int(config.get("stale_after_days") or 90)
        parameters["stale_cutoff"] = (date.today() - timedelta(days=stale_days)).isoformat()
        expressions.append(f"SUM(CASE WHEN TIMESTAMP(`{updated_at_column}`) < TIMESTAMP(@stale_cutoff) THEN 1 ELSE 0 END) AS stale_record_count")
    elif "stale_record_count" in manifest.outputs:
        warnings.append("No updated_at_column configured; stale_record_count was not returned.")
    query = f"SELECT {', '.join(expressions)} FROM `{table}`"
    return {
        "query": query,
        "parameters": parameters,
        "tables_referenced": [table],
        "query_template": manifest.manifest_id,
        "warnings": warnings + _allowlist_warnings(config, table_name),
    }


def _buyer_signal_query_plan(config: dict[str, Any], manifest: QueryManifest, params: dict[str, Any], *, project_id: str, dataset: str) -> dict[str, Any]:
    table, table_name = _configured_table(config, "buyer_signals_table", "buyer_signals", project_id=project_id, dataset=dataset)
    expressions = []
    if "buyer_signal_count" in manifest.outputs:
        expressions.append("COUNT(*) AS buyer_signal_count")
    strength_column = _optional_column(config, "signal_strength_column", "strength")
    if strength_column and "avg_signal_strength" in manifest.outputs:
        expressions.append(f"AVG(CAST(`{strength_column}` AS FLOAT64)) AS avg_signal_strength")
    account_column = _optional_column(config, "signal_account_id_column", "account_id")
    if account_column and "accounts" in manifest.outputs:
        expressions.append(f"COUNT(DISTINCT `{account_column}`) AS accounts")
    contact_column = _optional_column(config, "signal_contact_id_column", "contact_id")
    if contact_column and "contacts" in manifest.outputs:
        expressions.append(f"COUNT(DISTINCT `{contact_column}`) AS contacts")
    observed_at_column = _optional_column(config, "signal_observed_at_column", "observed_at")
    parameters = {"start_date": str(params["start_date"]), "end_date": str(params["end_date"])}
    where = f"WHERE DATE(`{observed_at_column}`) BETWEEN DATE(@start_date) AND DATE(@end_date)" if observed_at_column else ""
    query = f"SELECT {', '.join(expressions or ['COUNT(*) AS buyer_signal_count'])} FROM `{table}` {where}".strip()
    return {
        "query": query,
        "parameters": parameters,
        "tables_referenced": [table],
        "query_template": manifest.manifest_id,
        "warnings": _allowlist_warnings(config, table_name),
    }


def _campaign_outcome_query_plan(config: dict[str, Any], manifest: QueryManifest, params: dict[str, Any], *, project_id: str, dataset: str) -> dict[str, Any]:
    table, table_name = _configured_table(config, "campaign_outcomes_table", "campaign_outcomes", project_id=project_id, dataset=dataset)
    metric_columns = {
        "leads": "leads_column",
        "opportunities": "opportunities_column",
        "pipeline_amount": "pipeline_amount_column",
        "closed_won_revenue": "closed_won_revenue_column",
    }
    expressions = []
    warnings = []
    for metric, config_key in metric_columns.items():
        column = _optional_column(config, config_key, metric)
        if metric in manifest.outputs and column:
            expressions.append(f"SUM(CAST(`{column}` AS FLOAT64)) AS {metric}")
    if "conversion_rate" in manifest.outputs:
        conversions_column = _optional_column(config, "conversions_column", "conversions")
        clicks_column = _optional_column(config, "clicks_column", "clicks")
        if conversions_column and clicks_column:
            expressions.append(f"SAFE_DIVIDE(SUM(CAST(`{conversions_column}` AS FLOAT64)), NULLIF(SUM(CAST(`{clicks_column}` AS FLOAT64)), 0)) AS conversion_rate")
        else:
            warnings.append("No conversions_column/clicks_column configured; conversion_rate was not returned.")
    date_column = _optional_column(config, "campaign_outcome_date_column", "date")
    parameters = {"start_date": str(params["start_date"]), "end_date": str(params["end_date"])}
    where = f"WHERE DATE(`{date_column}`) BETWEEN DATE(@start_date) AND DATE(@end_date)" if date_column else ""
    query = f"SELECT {', '.join(expressions or ['COUNT(*) AS row_count'])} FROM `{table}` {where}".strip()
    return {
        "query": query,
        "parameters": parameters,
        "tables_referenced": [table],
        "query_template": manifest.manifest_id,
        "warnings": warnings + _allowlist_warnings(config, table_name),
    }


def _configured_table(config: dict[str, Any], key: str, default: str, *, project_id: str, dataset: str) -> tuple[str, str]:
    raw = str(config.get(key) or default)
    parts = raw.split(".")
    if len(parts) == 1:
        table_name = _identifier(parts[0], label=key)
        table = f"{_project(project_id)}.{_identifier(dataset, label='dataset')}.{table_name}"
    elif len(parts) == 3:
        table = f"{_project(parts[0])}.{_identifier(parts[1], label='dataset')}.{_identifier(parts[2], label=key)}"
        table_name = parts[2]
    else:
        raise RuntimeError(f"{key} must be a bare table name or project.dataset.table")
    allowed = _allowed_tables(config)
    if allowed and table_name not in allowed and table not in allowed:
        raise RuntimeError(f"BigQuery table {table_name} is not in allowed_tables for this client capsule.")
    return table, table_name


def _configured_tables(config: dict[str, Any]) -> dict[str, str]:
    return {
        key: str(config[key])
        for key in ("contacts_table", "buyer_signals_table", "campaign_outcomes_table")
        if config.get(key)
    }


def _allowed_tables(config: dict[str, Any]) -> list[str]:
    return [str(item) for item in config.get("allowed_tables", [])]


def _allowlist_warnings(config: dict[str, Any], table_name: str) -> list[str]:
    return [] if _allowed_tables(config) else [f"No allowed_tables configured; generated query used {table_name}."]


def _optional_column(config: dict[str, Any], key: str, default: str) -> str:
    value = str(config.get(key) if key in config else default).strip()
    return _identifier(value, label=key) if value else ""


def _identifier(value: str, *, label: str) -> str:
    text = str(value).strip()
    if not _IDENTIFIER_RE.match(text):
        raise RuntimeError(f"Invalid BigQuery {label}: {value!r}. Use simple SQL identifiers only.")
    return text


def _project(value: str) -> str:
    text = str(value).strip()
    if not _PROJECT_RE.match(text):
        raise RuntimeError(f"Invalid BigQuery project id: {value!r}.")
    return text


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _metrics_from_row(row: dict[str, Any], outputs: list[str]) -> dict[str, float | int | str]:
    metrics: dict[str, float | int | str] = {}
    for output in outputs:
        if output in row and row[output] is not None:
            metrics[output] = _coerce_metric(row[output])
    return metrics


def _coerce_metric(value: Any) -> float | int | str:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        if isinstance(value, str):
            try:
                number = float(value)
            except ValueError:
                return value
            return int(number) if number.is_integer() else round(number, 4)
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return int(number) if number.is_integer() else round(number, 4)


def _summary_for_manifest(manifest: QueryManifest, metrics: dict[str, Any], tables: list[str]) -> str:
    metric_summary = ", ".join(f"{key}={value}" for key, value in sorted(metrics.items())) or "no returned metrics"
    return f"BigQuery {manifest.manifest_id} read {', '.join(tables)} and returned {metric_summary}."


def _job_labels(capsule: ClientCapsule, manifest_id: str) -> dict[str, str]:
    return {
        "praxis_client": _label_value(capsule.client_id),
        "praxis_manifest": _label_value(manifest_id),
        "praxis_provider": "bigquery",
    }


def _label_value(value: str) -> str:
    text = re.sub(r"[^a-z0-9_-]+", "_", value.lower()).strip("_")
    return text[:63] or "praxis"
