"""Small 2026-03 HubSpot CRM client for read-only Reach queries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request

from .base import retry_operation


Transport = Callable[[str, str, dict[str, str], dict[str, Any], int], dict[str, Any]]


class HubSpotClientError(RuntimeError):
    """Raised when HubSpot returns an API or transport error."""


@dataclass(frozen=True)
class HubSpotPage:
    rows: list[dict[str, Any]]
    total: int
    truncated: bool = False
    pages_read: int = 0


class HubSpotClient:
    """Thin wrapper around HubSpot CRM object search.

    The wrapper intentionally does not expose write methods. Reach should query
    source systems, create aggregate evidence, and avoid becoming a shadow CRM.
    """

    api_version = "2026-03"

    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.hubapi.com",
        timeout: int = 20,
        max_retries: int = 3,
        transport: Transport | None = None,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(1, int(max_retries))
        self.transport = transport or self._default_transport

    def search(
        self,
        object_type: str,
        *,
        filters: list[dict[str, Any]] | None = None,
        properties: list[str] | None = None,
        limit: int = 200,
        after: str | None = None,
        sorts: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "limit": max(1, min(int(limit), 200)),
            "filterGroups": [{"filters": filters or []}],
            "properties": properties or [],
        }
        if after:
            payload["after"] = str(after)
        if sorts:
            payload["sorts"] = sorts
        path = f"/crm/objects/{self.api_version}/{object_type}/search"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        return retry_operation(
            lambda: self.transport("POST", f"{self.base_url}{path}", headers, payload, self.timeout),
            attempts=self.max_retries,
            label=f"HubSpot {object_type} search",
        )

    def collect_search(
        self,
        object_type: str,
        *,
        filters: list[dict[str, Any]] | None = None,
        properties: list[str] | None = None,
        limit: int = 200,
        max_pages: int = 50,
        sorts: list[str] | None = None,
    ) -> HubSpotPage:
        rows: list[dict[str, Any]] = []
        total = 0
        after: str | None = None
        pages_read = 0
        truncated = False
        while True:
            page = self.search(
                object_type,
                filters=filters,
                properties=properties,
                limit=limit,
                after=after,
                sorts=sorts,
            )
            pages_read += 1
            total = int(page.get("total") or total or 0)
            rows.extend([dict(item) for item in page.get("results") or [] if isinstance(item, dict)])
            after = _next_after(page)
            if not after:
                break
            if pages_read >= max_pages:
                truncated = True
                break
        return HubSpotPage(rows=rows, total=total, truncated=truncated, pages_read=pages_read)

    @staticmethod
    def _default_transport(
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=body, method=method, headers=headers)
        try:
            with request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            raise HubSpotClientError(_format_hubspot_error(exc.code, raw_error)) from exc
        except error.URLError as exc:
            raise HubSpotClientError(f"HubSpot request failed: {exc.reason}") from exc
        return json.loads(raw or "{}")


def _next_after(page: dict[str, Any]) -> str | None:
    paging = page.get("paging")
    if not isinstance(paging, dict):
        return None
    next_page = paging.get("next")
    if not isinstance(next_page, dict):
        return None
    after = next_page.get("after")
    return str(after) if after not in {None, ""} else None


def _format_hubspot_error(status_code: int, raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return f"HubSpot API returned HTTP {status_code}: {raw[:300]}"
    message = data.get("message") or data.get("error") or raw
    category = data.get("category")
    suffix = f" ({category})" if category else ""
    return f"HubSpot API returned HTTP {status_code}: {message}{suffix}"
