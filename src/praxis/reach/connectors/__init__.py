"""Connector registry for Praxis Reach."""

from __future__ import annotations

from .base import Connector, ConnectorDiscovery, ConnectorResult
from .bigquery import BigQueryConnector
from .fixture import FixtureAdsConnector, FixtureCRMConnector
from .google_analytics import GoogleAnalyticsConnector
from .google_ads import GoogleAdsConnector
from .hubspot import HubSpotConnector
from .mock import MockAdsConnector, MockCRMConnector


def available_connectors() -> dict[str, type[Connector]]:
    return {
        "mock_ads": MockAdsConnector,
        "mock_crm": MockCRMConnector,
        "fixture_ads": FixtureAdsConnector,
        "fixture_crm": FixtureCRMConnector,
        "bigquery": BigQueryConnector,
        "hubspot": HubSpotConnector,
        "google_ads": GoogleAdsConnector,
        "google_analytics": GoogleAnalyticsConnector,
    }


__all__ = ["Connector", "ConnectorDiscovery", "ConnectorResult", "available_connectors"]
