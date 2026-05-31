"""Small read-only Google Ads API client wrapper for Reach queries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .base import retry_operation


class GoogleAdsClientError(RuntimeError):
    """Raised when Google Ads returns an API or transport error."""


@dataclass(frozen=True)
class GoogleAdsRows:
    rows: list[Any]
    batches_read: int = 0
    truncated: bool = False


class GoogleAdsClient:
    """Thin wrapper around the official Google Ads Python client.

    The wrapper keeps Praxis Reach read-only and makes connector tests possible
    without importing the optional Google Ads dependency.
    """

    def __init__(
        self,
        *,
        configuration_file: str = "",
        configuration_dict: dict[str, Any] | None = None,
        login_customer_id: str = "",
        client: Any | None = None,
        max_retries: int = 3,
    ) -> None:
        self.configuration_file = configuration_file
        self.configuration_dict = configuration_dict
        self.login_customer_id = clean_customer_id(login_customer_id)
        self._client = client
        self.max_retries = max(1, int(max_retries))

    def sdk_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.ads.googleads.client import GoogleAdsClient as SDKGoogleAdsClient  # type: ignore
        except ImportError as exc:
            raise GoogleAdsClientError('Install the optional dependency with `python3 -m pip install "praxis-ktos[google-ads]"`.') from exc

        if self.configuration_dict:
            client = SDKGoogleAdsClient.load_from_dict(self.configuration_dict)
        elif self.configuration_file:
            client = SDKGoogleAdsClient.load_from_storage(self.configuration_file)
        else:
            client = SDKGoogleAdsClient.load_from_storage()
        if self.login_customer_id:
            client.login_customer_id = self.login_customer_id
        self._client = client
        return client

    def list_accessible_customers(self) -> list[str]:
        try:
            response = retry_operation(
                lambda: self.sdk_client().get_service("CustomerService").list_accessible_customers(),
                attempts=self.max_retries,
                label="Google Ads accessible-customer check",
            )
        except Exception as exc:  # pragma: no cover - concrete SDK exceptions vary by installed version.
            raise GoogleAdsClientError(f"Google Ads accessible-customer check failed: {exc}") from exc
        return [str(item) for item in getattr(response, "resource_names", [])]

    def list_customer_clients(self, manager_customer_id: str, *, max_batches: int = 100) -> list[dict[str, Any]]:
        query = """
            SELECT
              customer_client.client_customer,
              customer_client.descriptive_name,
              customer_client.manager,
              customer_client.level,
              customer_client.status,
              customer_client.currency_code,
              customer_client.time_zone
            FROM customer_client
            WHERE customer_client.level <= 1
        """
        report = self.search_stream(manager_customer_id, query, max_batches=max_batches)
        customers: list[dict[str, Any]] = []
        for row in report.rows:
            value = row.get("customer_client") if isinstance(row, dict) else getattr(row, "customer_client", None)
            if value is None:
                continue
            customers.append(
                {
                    "resource_name": _field(value, "client_customer"),
                    "id": clean_customer_id(_field(value, "client_customer")),
                    "name": _field(value, "descriptive_name"),
                    "manager": bool(_field(value, "manager")),
                    "level": _field(value, "level"),
                    "status": _field(value, "status"),
                    "currency_code": _field(value, "currency_code"),
                    "time_zone": _field(value, "time_zone"),
                }
            )
        return customers

    def search_stream(self, customer_id: str, query: str, *, max_batches: int = 100) -> GoogleAdsRows:
        customer_id = clean_customer_id(customer_id)
        if not customer_id:
            raise GoogleAdsClientError("Google Ads customer_id is required.")
        try:
            stream = retry_operation(
                lambda: self.sdk_client().get_service("GoogleAdsService").search_stream(customer_id=customer_id, query=query),
                attempts=self.max_retries,
                label="Google Ads search_stream",
            )
        except Exception as exc:  # pragma: no cover - concrete SDK exceptions vary by installed version.
            raise GoogleAdsClientError(f"Google Ads query failed: {exc}") from exc

        rows: list[Any] = []
        batches_read = 0
        truncated = False
        try:
            for batch in stream:
                batches_read += 1
                rows.extend(list(getattr(batch, "results", [])))
                if batches_read >= max(1, int(max_batches)):
                    truncated = True
                    break
        except Exception as exc:  # pragma: no cover - stream errors are SDK-specific.
            raise GoogleAdsClientError(f"Google Ads stream read failed: {exc}") from exc
        return GoogleAdsRows(rows=rows, batches_read=batches_read, truncated=truncated)


def clean_customer_id(value: str | int | None) -> str:
    """Return the numeric Google Ads customer id without dashes or prefixes."""

    if value in {None, ""}:
        return ""
    text = str(value)
    if text.startswith("customers/"):
        text = text.split("/", 1)[1]
    return re.sub(r"[^0-9]", "", text)


def _field(value: Any, name: str) -> str:
    if isinstance(value, dict):
        return str(value.get(name) or "")
    return str(getattr(value, name, "") or "")
