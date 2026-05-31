# Google Analytics Connector

The Google Analytics connector is a read-only Praxis Reach connector for GA4 website and app analytics evidence.

It lets a client capsule point Praxis at a GA4 property, run approved aggregate Data API reports, and keep the resulting evidence source-linked without copying raw user-level analytics data into Praxis.

## What It Does

- Uses client capsule property and credential references, not stored secrets.
- Uses the GA4 Data API through a small `GoogleAnalyticsClient` wrapper.
- Uses the Google Analytics Admin API for optional account/property discovery.
- Runs aggregate reports for selected date windows.
- Captures GA4 quota metadata when returned by the Data API.
- Filters key-event/conversion metrics through client-specific conversion definitions when configured.
- Produces metrics such as sessions, active users, total users, event count, key events, conversions, revenue, engagement rate, and conversion rate.
- Stores source links, warnings, connector metadata, row counts, and aggregate summaries.
- Leaves raw event/user data inside Google Analytics.

## Install

The connector depends on the official Google Analytics Data API package. Account/property discovery also uses the Google Analytics Admin package:

```bash
python3 -m pip install "praxis-ktos[google-analytics]"
```

## Environment

Client capsules store environment variable names. They do not store credentials.

For a client named `acme`, Praxis generates:

```bash
export GOOGLE_ANALYTICS_ACME_PROPERTY_ID="123456789"
export GOOGLE_ANALYTICS_ACME_CREDENTIALS_FILE="/path/to/service-account.json"
```

If no client-specific values are present, the connector can fall back to:

```bash
export GOOGLE_ANALYTICS_PROPERTY_ID="123456789"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

If `GOOGLE_APPLICATION_CREDENTIALS` is not set, live calls may still work when Application Default Credentials are configured in the local environment.

## Commands

```bash
praxis reach init
praxis agency client create acme --crm hubspot --ads google_ads --analytics google_analytics
praxis agency client doctor acme
praxis reach connectors test google_analytics --client acme
praxis reach connectors test google_analytics --client acme --live
praxis reach connectors discover google_analytics --client acme --live
praxis agency client define-conversion acme ga4_lead --source google_analytics --source-name generate_lead
praxis reach query run website_performance --client acme --days 30
praxis reach evidence show "ev:..."
```

`praxis reach connectors test google_analytics --client acme` is a static check. It verifies local configuration only and does not call Google Analytics.

`praxis reach connectors test google_analytics --client acme --live` makes a small GA4 Data API report call to verify property access.

`praxis reach connectors discover google_analytics --client acme --live` uses the Admin API account-summary endpoint to list accessible accounts and properties.

## Current Metrics

The connector can currently produce:

- `sessions`
- `active_users`
- `total_users`
- `event_count`
- `key_events`
- `conversions`
- `revenue`
- `engagement_rate`
- `conversion_rate`

GA4 key-event and revenue definitions are account-specific. Confirm those definitions before treating analytics conversions as canonical business truth.

Client conversion mappings let a team define which GA4 events count as useful business conversions:

```bash
praxis agency client define-conversion acme ga4_lead \
  --source google_analytics \
  --source-name generate_lead \
  --canonical-metric conversions
```

When mappings exist, Praxis filters `key_events`, `conversions`, and `conversion_rate` through those mappings. Without mappings, GA4 key events are treated as account-level directional signals.

## Safety Notes

- Keep service account files and OAuth credentials outside Praxis files.
- Store aggregate evidence cards, not raw analytics exports.
- Treat analytics conversions as directional until reconciled against CRM-confirmed leads, pipeline, or revenue.
- Use client capsules to keep per-client property IDs and credential references separate.
