# Google Ads Connector

The Google Ads connector is a read-only Praxis Reach connector for aggregate paid-media evidence.

It is designed to query Google Ads directly, create source-linked evidence cards, and avoid cloning campaign exports into Praxis.

## Current Status

The current connector can:

- declare Google Ads capabilities;
- introspect the expected campaign metric fields;
- run an aggregate campaign-performance query for a requested date window;
- use a small `GoogleAdsClient` wrapper around the official Google Ads Python client;
- run static setup checks and optional live accessible-customer checks;
- discover configured customers, accessible customers, and manager-account children where permissions allow;
- filter conversion metrics through client-specific conversion definitions;
- return spend, impressions, clicks, CTR, CPC, CPM, conversions, conversion value, conversion rate, warnings, source links, and connector metadata;
- store aggregate evidence only.

It does not yet:

- reconcile Google Ads conversions against CRM-confirmed pipeline as a hard truth decision;
- store raw row-level exports by default;
- write back to campaigns.

## Install

The Google Ads connector depends on the official `google-ads` Python package:

```bash
python3 -m pip install "praxis-ktos[google-ads]"
```

## Environment

Client capsules store credential and account references, not secrets. For a client named `acme`, Praxis generates client-specific env var references:

```bash
export GOOGLE_ADS_ACME_CONFIGURATION_FILE="/path/to/google-ads.yaml"
export GOOGLE_ADS_ACME_CUSTOMER_ID="1234567890"
export GOOGLE_ADS_ACME_LOGIN_CUSTOMER_ID="9876543210" # optional manager account
```

If no client-specific env vars are configured, the connector can fall back to:

```bash
export GOOGLE_ADS_CONFIGURATION_FILE="/path/to/google-ads.yaml"
export GOOGLE_ADS_CUSTOMER_ID="1234567890"
export GOOGLE_ADS_LOGIN_CUSTOMER_ID="9876543210" # optional
```

## Example

```bash
praxis reach init
praxis agency client create acme --crm mock_crm --ads google_ads
praxis agency client doctor acme
praxis reach connectors test google_ads --client acme
praxis reach connectors test google_ads --client acme --live
praxis reach connectors discover google_ads --client acme --live
praxis agency client define-conversion acme lead_form --source google_ads --source-name "Lead Form Submit"
praxis reach query run reach_historical --client acme --days 90
praxis reach query run reach_historical --client acme --start-date 2026-01-01 --end-date 2026-01-31
praxis reach evidence show "ev:..."
```

`praxis reach connectors test google_ads --client acme` is a static check. It verifies local configuration only and does not call Google Ads.

`praxis reach connectors test google_ads --client acme --live` calls the accessible-customer endpoint to verify that the credentials can reach the API. Manager-account setups may still require manual customer-id verification.

`praxis reach connectors discover google_ads --client acme --live` lists accessible customer resources and, when `login_customer_id` is configured, manager child accounts.

## Query Shape

The current report template reads campaign-level aggregate metrics:

```sql
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
WHERE segments.date BETWEEN @start_date AND @end_date
```

Praxis aggregates those rows into evidence metrics and stores row counts, connector version, query template, source link, and warnings.

When client conversion definitions exist, Praxis also runs a conversion-action report and filters `conversions` / `conversion_value` to the mapped conversion actions:

```bash
praxis agency client define-conversion acme lead_form \
  --source google_ads \
  --source-name "Lead Form Submit" \
  --canonical-metric conversions
```

Without mappings, Google Ads conversion metrics are treated as platform-level directional signals.

## Safety Notes

- Start with read-only Google Ads access.
- Keep credentials outside Praxis files.
- Treat ad-platform lead and conversion numbers as directional until CRM-confirmed.
- Use Reach conflict warnings when Google Ads and CRM disagree.
- Store aggregate evidence cards, not full campaign exports.
