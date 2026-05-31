# HubSpot Connector

The HubSpot connector is a read-only Praxis Reach connector for pulling live CRM evidence into evidence cards without copying HubSpot into Praxis.

It uses HubSpot's dated `2026-03` CRM object search API through a small `HubSpotClient` wrapper.

## What It Does

- Uses client capsule credential references, not stored secrets.
- Reads client-specific field maps from `field_map.json`.
- Searches HubSpot contacts and deals with pagination.
- Aggregates CRM data into metrics such as leads, opportunities, pipeline amount, and closed-won revenue.
- Stores only aggregate evidence, source links, warnings, metadata, and connector versions.
- Leaves raw contacts, deals, and PII inside HubSpot.

## Current Metrics

The connector can currently produce:

- `leads`: contacts created in the selected date window.
- `mqls`: contacts whose lifecycle stage matches the client's MQL definition.
- `sqls`: contacts whose lifecycle stage matches the client's SQL definition.
- `opportunities`: deals created in the selected date window.
- `pipeline_amount`: non-lost deal amount from deals created in the selected date window.
- `closed_won_revenue`: closed-won deal amount from deals whose close date falls in the selected date window.

Lifecycle and stage definitions are client-specific. Set them in `metrics.json` before treating MQL, SQL, or pipeline metrics as canonical.

## Static Token Setup

Client capsules store environment variable names. They do not store tokens.

For a client named `acme`, Praxis generates:

```bash
export HUBSPOT_ACME_ACCESS_TOKEN="..."
```

If no client-specific token is present, the connector can fall back to:

```bash
export HUBSPOT_ACCESS_TOKEN="..."
```

Use the narrowest read-only CRM scopes available for contacts and deals.

## Commands

```bash
praxis reach init
praxis agency client create acme --crm hubspot --ads mock_ads
praxis agency client map-fields acme
praxis agency client metrics acme
praxis reach connectors test hubspot --client acme
praxis reach connectors test hubspot --client acme --live
praxis reach query run pipeline_health --client acme --days 90
praxis reach evidence show "ev:..."
```

`praxis reach connectors test hubspot --client acme` is a static check. It verifies local configuration only and does not call HubSpot.

`praxis reach connectors test hubspot --client acme --live` makes a small CRM search call to verify the token and read scope.

## Field Maps

For HubSpot clients, the default CRM mapping is:

```json
{
  "contact": {
    "source": "hubspot.contacts",
    "fields": {
      "id": "hs_object_id",
      "created_at": "createdate",
      "lifecycle_stage": "lifecyclestage",
      "source": "hs_analytics_source"
    }
  },
  "opportunity": {
    "source": "hubspot.deals",
    "fields": {
      "id": "hs_object_id",
      "created_at": "createdate",
      "amount": "amount",
      "stage": "dealstage",
      "close_date": "closedate",
      "pipeline": "pipeline",
      "source": "hubspot_owner_id"
    }
  }
}
```

Use `praxis agency client map-fields` if a client has custom fields.

## Pagination

The connector uses HubSpot search pagination and reads up to `max_pages` pages per object search.

Set `max_pages` in the HubSpot system entry in `systems.json` if a client needs a larger or smaller cap:

```json
{
  "provider": "hubspot",
  "auth_mode": "static_token",
  "credential_env": "HUBSPOT_ACME_ACCESS_TOKEN",
  "max_pages": 50
}
```

If a query reaches the page cap, the evidence card includes a warning that metrics may be partial.

## OAuth Design

OAuth is planned, but not implemented yet. Static token mode should stay boring and reliable first.

The intended OAuth shape is:

- `auth_mode: oauth` in the client capsule.
- A per-client token reference, not raw tokens in Praxis files.
- Access token refresh handled by an adapter or secrets provider.
- HubSpot install and refresh flows using the 2026-03 OAuth token endpoint.
- The same read-only `HubSpotClient` interface after token resolution.

This means the connector should not care whether the token came from a private app token, a short-lived OAuth access token, or a secrets manager. It should receive a bearer token and stay read-only.

## Safety Notes

- Do not store HubSpot tokens in Praxis files.
- Do not store raw contact or deal exports in evidence cards.
- Treat HubSpot as the source of truth.
- Treat Praxis evidence as a source-linked aggregate snapshot.
- Use `--live` deliberately because it calls the provider API.
