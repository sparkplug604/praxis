"""Small read-only Google Analytics Data API client wrapper for Reach."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import retry_operation


class GoogleAnalyticsClientError(RuntimeError):
    """Raised when Google Analytics returns an API or transport error."""


@dataclass(frozen=True)
class GoogleAnalyticsReport:
    rows: list[dict[str, Any]]
    row_count: int = 0
    metadata: dict[str, Any] | None = None


class GoogleAnalyticsClient:
    """Thin wrapper around the GA4 Data API.

    Praxis asks GA4 for aggregate reports and stores evidence summaries, not raw
    user-level analytics exports.
    """

    def __init__(
        self,
        *,
        credentials_file: str = "",
        data_client: Any | None = None,
        admin_client: Any | None = None,
        max_retries: int = 3,
    ) -> None:
        self.credentials_file = credentials_file
        self._data_client = data_client
        self._admin_client = admin_client
        self.max_retries = max(1, int(max_retries))

    def data_client(self) -> Any:
        if self._data_client is not None:
            return self._data_client
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient  # type: ignore
        except ImportError as exc:
            raise GoogleAnalyticsClientError(
                'Install the optional dependency with `python3 -m pip install "praxis-ktos[google-analytics]"`.'
            ) from exc
        if self.credentials_file and hasattr(BetaAnalyticsDataClient, "from_service_account_file"):
            self._data_client = BetaAnalyticsDataClient.from_service_account_file(self.credentials_file)
        else:
            self._data_client = BetaAnalyticsDataClient()
        return self._data_client

    def admin_client(self) -> Any:
        if self._admin_client is not None:
            return self._admin_client
        try:
            try:
                from google.analytics.admin import AnalyticsAdminServiceClient  # type: ignore
            except ImportError:
                from google.analytics.admin_v1beta import AnalyticsAdminServiceClient  # type: ignore
        except ImportError as exc:
            raise GoogleAnalyticsClientError(
                'Install the optional dependency with `python3 -m pip install "praxis-ktos[google-analytics]"`.'
            ) from exc
        if self.credentials_file and hasattr(AnalyticsAdminServiceClient, "from_service_account_file"):
            self._admin_client = AnalyticsAdminServiceClient.from_service_account_file(self.credentials_file)
        else:
            self._admin_client = AnalyticsAdminServiceClient()
        return self._admin_client

    def list_account_summaries(self, *, page_size: int = 200) -> list[dict[str, Any]]:
        try:
            response = retry_operation(
                lambda: self.admin_client().list_account_summaries(page_size=max(1, int(page_size))),
                attempts=self.max_retries,
                label="Google Analytics account-summary discovery",
            )
        except Exception as exc:  # pragma: no cover - concrete SDK exceptions vary by installed version.
            raise GoogleAnalyticsClientError(f"Google Analytics account-summary discovery failed: {exc}") from exc
        resources: list[dict[str, Any]] = []
        for account in response:
            account_name = str(getattr(account, "account", "") or "")
            account_display_name = str(getattr(account, "display_name", "") or "")
            resources.append(
                {
                    "kind": "account",
                    "resource_name": account_name,
                    "id": account_name.rsplit("/", 1)[-1],
                    "name": account_display_name,
                }
            )
            for property_summary in getattr(account, "property_summaries", []) or []:
                property_name = str(getattr(property_summary, "property", "") or "")
                resources.append(
                    {
                        "kind": "property",
                        "resource_name": property_name,
                        "id": property_name.rsplit("/", 1)[-1],
                        "name": str(getattr(property_summary, "display_name", "") or ""),
                        "account": account_name,
                        "account_name": account_display_name,
                    }
                )
        return resources

    def run_report(
        self,
        *,
        property_id: str,
        metrics: list[str],
        dimensions: list[str] | None = None,
        start_date: str,
        end_date: str,
        limit: int = 1000,
    ) -> GoogleAnalyticsReport:
        property_name = normalize_property_id(property_id)
        dimensions = dimensions or []
        if self._data_client is not None:
            response = self._data_client.run_report(
                {
                    "property": property_name,
                    "metrics": metrics,
                    "dimensions": dimensions,
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": limit,
                    "return_property_quota": True,
                }
            )
            return _report_from_response(response, metrics=metrics, dimensions=dimensions)

        try:
            from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest  # type: ignore
        except ImportError as exc:
            raise GoogleAnalyticsClientError(
                'Install the optional dependency with `python3 -m pip install "praxis-ktos[google-analytics]"`.'
            ) from exc

        request = RunReportRequest(
            property=property_name,
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[Metric(name=item) for item in metrics],
            dimensions=[Dimension(name=item) for item in dimensions],
            limit=max(1, int(limit)),
            return_property_quota=True,
        )
        try:
            response = retry_operation(
                lambda: self.data_client().run_report(request),
                attempts=self.max_retries,
                label="Google Analytics runReport",
            )
        except Exception as exc:  # pragma: no cover - concrete SDK exceptions vary by installed version.
            raise GoogleAnalyticsClientError(f"Google Analytics runReport failed: {exc}") from exc
        return _report_from_response(response, metrics=metrics, dimensions=dimensions)


def normalize_property_id(value: str | int) -> str:
    text = str(value).strip()
    if text.startswith("properties/"):
        return text
    return f"properties/{text}"


def _report_from_response(response: Any, *, metrics: list[str], dimensions: list[str]) -> GoogleAnalyticsReport:
    if isinstance(response, GoogleAnalyticsReport):
        return response
    if isinstance(response, dict):
        rows = [dict(item) for item in response.get("rows", []) if isinstance(item, dict)]
        return GoogleAnalyticsReport(rows=rows, row_count=int(response.get("row_count") or len(rows)), metadata=dict(response.get("metadata") or {}))

    rows: list[dict[str, Any]] = []
    for row in getattr(response, "rows", []) or []:
        metric_values = getattr(row, "metric_values", []) or []
        dimension_values = getattr(row, "dimension_values", []) or []
        rows.append(
            {
                "metrics": {
                    metric: _typed_value(metric_values[index].value)
                    for index, metric in enumerate(metrics)
                    if index < len(metric_values)
                },
                "dimensions": {
                    dimension: dimension_values[index].value
                    for index, dimension in enumerate(dimensions)
                    if index < len(dimension_values)
                },
            }
        )
    row_count = int(getattr(response, "row_count", 0) or len(rows))
    metadata = {
        "property_quota": _message_to_dict(getattr(response, "property_quota", None)),
        "kind": getattr(response, "kind", ""),
    }
    return GoogleAnalyticsReport(rows=rows, row_count=row_count, metadata=metadata)


def _typed_value(value: str) -> float | int | str:
    text = str(value)
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return int(number)
    return number


def _message_to_dict(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        return {
            field.name: getattr(value, field.name)
            for field in value.DESCRIPTOR.fields
        }
    except Exception:
        return {"raw": str(value)}
