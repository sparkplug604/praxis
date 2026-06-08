"""Small read-only BigQuery client wrapper for Praxis Reach."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import retry_operation


class BigQueryClientError(RuntimeError):
    """Raised when BigQuery returns an API, dependency, or transport error."""


@dataclass(frozen=True)
class BigQueryRows:
    rows: list[dict[str, Any]]
    row_count: int = 0
    metadata: dict[str, Any] | None = None


class BigQueryClient:
    """Thin wrapper around BigQuery query jobs.

    Reach uses BigQuery as a read-only warehouse source. The wrapper exposes
    dry-run estimation and aggregate query execution, not write operations.
    """

    def __init__(
        self,
        *,
        project_id: str = "",
        credentials_file: str = "",
        location: str = "",
        client: Any | None = None,
        max_retries: int = 3,
    ) -> None:
        self.project_id = project_id
        self.credentials_file = credentials_file
        self.location = location or None
        self._client = client
        self.max_retries = max(1, int(max_retries))

    def client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import bigquery  # type: ignore
        except ImportError as exc:
            raise BigQueryClientError('Install the optional dependency with `python3 -m pip install "praxis-ktos[bigquery]"`.') from exc
        if self.credentials_file:
            self._client = bigquery.Client.from_service_account_json(self.credentials_file, project=self.project_id or None)
        else:
            self._client = bigquery.Client(project=self.project_id or None)
        return self._client

    def dry_run(
        self,
        query: str,
        *,
        parameters: dict[str, Any] | None = None,
        maximum_bytes_billed: int | None = None,
        labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            from google.cloud import bigquery  # type: ignore
        except ImportError as exc:
            raise BigQueryClientError('Install the optional dependency with `python3 -m pip install "praxis-ktos[bigquery]"`.') from exc
        job_config = bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            maximum_bytes_billed=maximum_bytes_billed,
            query_parameters=_query_parameters(bigquery, parameters or {}),
            labels=labels or {},
        )
        try:
            job = retry_operation(
                lambda: self.client().query(query, job_config=job_config, location=self.location),
                attempts=self.max_retries,
                label="BigQuery dry run",
            )
        except Exception as exc:  # pragma: no cover - concrete SDK exceptions vary by installed version.
            raise BigQueryClientError(f"BigQuery dry run failed: {exc}") from exc
        return {
            "job_id": str(getattr(job, "job_id", "") or ""),
            "total_bytes_processed": int(getattr(job, "total_bytes_processed", 0) or 0),
            "location": str(getattr(job, "location", "") or self.location or ""),
        }

    def query(
        self,
        query: str,
        *,
        parameters: dict[str, Any] | None = None,
        maximum_bytes_billed: int | None = None,
        labels: dict[str, str] | None = None,
    ) -> BigQueryRows:
        try:
            from google.cloud import bigquery  # type: ignore
        except ImportError as exc:
            raise BigQueryClientError('Install the optional dependency with `python3 -m pip install "praxis-ktos[bigquery]"`.') from exc
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=maximum_bytes_billed,
            query_parameters=_query_parameters(bigquery, parameters or {}),
            labels=labels or {},
        )
        try:
            job = retry_operation(
                lambda: self.client().query(query, job_config=job_config, location=self.location),
                attempts=self.max_retries,
                label="BigQuery query",
            )
            rows_iterable = retry_operation(
                lambda: job.result(),
                attempts=self.max_retries,
                label="BigQuery query result",
            )
        except Exception as exc:  # pragma: no cover - concrete SDK exceptions vary by installed version.
            raise BigQueryClientError(f"BigQuery query failed: {exc}") from exc
        rows = [_row_to_dict(row) for row in rows_iterable]
        return BigQueryRows(
            rows=rows,
            row_count=int(getattr(rows_iterable, "total_rows", 0) or len(rows)),
            metadata={
                "job_id": str(getattr(job, "job_id", "") or ""),
                "total_bytes_processed": int(getattr(job, "total_bytes_processed", 0) or 0),
                "cache_hit": bool(getattr(job, "cache_hit", False)),
                "slot_millis": int(getattr(job, "slot_millis", 0) or 0),
                "location": str(getattr(job, "location", "") or self.location or ""),
            },
        )

    def list_tables(self, *, project_id: str, dataset: str, include_columns: bool = False) -> list[dict[str, Any]]:
        dataset_ref = f"{project_id}.{dataset}"
        try:
            tables = retry_operation(
                lambda: list(self.client().list_tables(dataset_ref)),
                attempts=self.max_retries,
                label="BigQuery list tables",
            )
        except Exception as exc:  # pragma: no cover - concrete SDK exceptions vary by installed version.
            raise BigQueryClientError(f"BigQuery table discovery failed: {exc}") from exc
        resources: list[dict[str, Any]] = []
        for table in tables:
            table_id = str(getattr(table, "table_id", "") or "")
            resource = {
                "kind": "table",
                "id": table_id,
                "resource_name": f"{dataset_ref}.{table_id}",
            }
            if include_columns and table_id:
                resource["columns"] = self.table_columns(project_id=project_id, dataset=dataset, table=table_id)
            resources.append(resource)
        return resources

    def table_columns(self, *, project_id: str, dataset: str, table: str) -> list[dict[str, str]]:
        table_ref = f"{project_id}.{dataset}.{table}"
        try:
            table_obj = retry_operation(
                lambda: self.client().get_table(table_ref),
                attempts=self.max_retries,
                label="BigQuery table schema",
            )
        except Exception as exc:  # pragma: no cover - concrete SDK exceptions vary by installed version.
            raise BigQueryClientError(f"BigQuery schema discovery failed for {table_ref}: {exc}") from exc
        columns = []
        for field in getattr(table_obj, "schema", []) or []:
            columns.append(
                {
                    "name": str(getattr(field, "name", "") or ""),
                    "type": str(getattr(field, "field_type", "") or ""),
                    "mode": str(getattr(field, "mode", "") or ""),
                }
            )
        return columns


def _query_parameters(bigquery: Any, parameters: dict[str, Any]) -> list[Any]:
    out = []
    for key, value in sorted(parameters.items()):
        out.append(bigquery.ScalarQueryParameter(str(key), _parameter_type(value), value))
    return out


def _parameter_type(value: Any) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    if isinstance(value, float):
        return "FLOAT64"
    return "STRING"


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "items"):
        return dict(row.items())
    return dict(row)
