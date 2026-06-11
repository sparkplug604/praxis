# Praxis Reach

Praxis Reach is the experimental live-data layer for Praxis.

Praxis Core turns source material into searchable, traceable, reusable agent knowledge. Praxis Reach extends that idea to operational systems: CRMs, ads platforms, analytics tools, revenue systems, and other sources of live business data.

Reach is designed around one rule:

> Keep the system of record where it is. Store evidence, not a shadow copy.

## What Reach Is For

Use Reach when the problem is not "the agent forgot our docs."

Use it when:

- the agent needs recent campaign, pipeline, or website-performance context;
- humans are manually exporting CSVs from multiple platforms;
- source data is too large, sensitive, or fast-changing to clone into a local RAG database;
- agents need fresh business context with links back to the real systems.

## What Reach Stores

Reach stores:

- connector metadata;
- client/account configuration;
- query manifests;
- source links;
- timestamps;
- freshness metadata;
- aggregate summaries;
- evidence cards;
- context packs.

Reach avoids storing:

- raw CRM exports by default;
- raw PII by default;
- full ad-platform clones;
- secrets or credentials;
- unbounded row-level data.

## Main Objects

| Object | Purpose |
| --- | --- |
| Connector | Read-only adapter for a live system such as a CRM, ads platform, or analytics tool. |
| Query manifest | Approved, parameterized query contract with required parameters, outputs, storage level, freshness SLA, and conflict checks. |
| Evidence card | Timestamped summary of a query result with source links, freshness, metrics, warnings, and conflict metadata. |
| Context pack | Compact Markdown context built from fresh evidence for agent work. |
| Metric ontology | Canonical GTM metric definitions such as reach, pipeline, SQL, ROAS, sessions, and conversions. |

## Current Connector Status

| Connector | Status |
| --- | --- |
| `fixture_crm` / `fixture_ads` | Works now for demos. |
| `mock_crm` / `mock_ads` | Works now for local testing. |
| `hubspot` | Experimental real connector. |
| `google_ads` | Experimental real connector. |
| `google_analytics` | Experimental real connector for GA4. |
| `bigquery` | Experimental real connector for warehouse-backed GTM evidence. |

The fixture connectors let the CLI, evidence-card model, context-pack generation, manifest validation, and agency capsule flow be tested before live credentials are introduced.

## First Run

No credentials required:

```bash
praxis demo reach
```

Or manually:

```bash
praxis reach init
praxis agency fixture create demo --profile b2b-saas --overwrite
praxis agency run weekly_gtm_review --clients demo --context
praxis reach evidence list --client demo
```

## What Init Creates

`praxis reach init` creates the local Reach workspace:

```text
workspace/
  reach/
    query_manifests/
    ontology/
    evidence/
    context_packs/
    fixtures/
  agency/
    clients/
```

Built-in query manifests include:

- `pipeline_health`
- `reach_historical`
- `weekly_gtm_review`
- `website_performance`
- `traffic_attribution_check`
- `full_gtm_signal_check`

Built-in context templates include:

- `pipeline_health_check`
- `reach_drop_diagnosis`
- `weekly_gtm_review`

## Common Reach Commands

| Command | What It Does |
| --- | --- |
| `praxis reach init` | Creates Reach folders and seeds built-in manifests. |
| `praxis reach doctor` | Checks Reach setup. |
| `praxis reach connectors list` | Lists installed connectors. |
| `praxis reach connectors inspect` | Shows connector capabilities. |
| `praxis reach connectors test` | Checks connector configuration for one client. |
| `praxis reach connectors discover` | Discovers accessible accounts/properties where supported. |
| `praxis reach query list` | Lists query manifests. |
| `praxis reach query run` | Runs a query and writes an evidence card. |
| `praxis reach evidence list` | Lists evidence cards. |
| `praxis reach evidence show` | Shows evidence details. |
| `praxis reach evidence refresh` | Reruns the query behind an evidence card. |
| `praxis reach evidence capture` | Captures an evidence card into Praxis Core. |
| `praxis reach stale list` | Reports stale or fresh evidence. |
| `praxis reach context build` | Builds an agent-ready context pack. |

## Evidence Lifecycle

Reach evidence cards can be inspected, refreshed, checked for staleness, and captured into Praxis Core:

```bash
praxis reach stale list --all
praxis reach evidence refresh "ev:..."
praxis reach evidence capture "ev:..."
```

`evidence capture` writes a Markdown representation of the evidence card and captures it through the normal Praxis Core source pipeline. This lets a live-data result become source-traceable knowledge without storing raw source-system data.

## Query Guardrails

Every Reach run is checked before an evidence card is written:

- the manifest must validate;
- required parameters such as `client_id`, `start_date`, and `end_date` must be present;
- date windows must use `YYYY-MM-DD`;
- the connector must declare `mode=read_only`;
- the connector must support the manifest storage level;
- the client capsule must allow the storage level;
- connector metrics must stay inside the manifest outputs.

This keeps Reach closer to a controlled evidence pipeline than a free-form data pull script.

## Connector Discovery And Conversion Mapping

Connectors that can enumerate configured source resources support discovery through the generic connector command:

```bash
praxis reach connectors discover google_ads --client acme --live
praxis reach connectors discover google_analytics --client acme --live
praxis reach connectors discover bigquery --client acme --live
```

Client-specific conversion definitions live in `metrics.json` and can be updated from the CLI:

```bash
praxis agency client define-conversion acme lead_form --source google_ads --source-name "Lead Form Submit"
praxis agency client define-conversion acme ga4_lead --source google_analytics --source-name generate_lead
```

When definitions exist, Praxis filters platform conversion metrics through those mappings before writing evidence. When definitions do not exist, evidence cards warn that platform conversions include all reported conversions/key events.

## Connector Setup

Use `praxis reach connectors test <provider> --client <client-id>` before running a live query.

The setup check verifies local configuration for that client, such as credential environment variable names, package availability, and connector readiness. It does not store secrets in Praxis files.

Connector docs:

- [HubSpot](../../connectors/hubspot.md)
- [Google Ads](../../connectors/google-ads.md)
- [Google Analytics / GA4](../../connectors/google-analytics.md)
- [BigQuery](../../connectors/bigquery.md)

## GTM Conflict Checks

Reach can attach GTM-specific conflict warnings to evidence cards. Current checks include:

- CRM-vs-ad-platform lead disagreement.
- Google Ads vs analytics conversion disagreement.
- Analytics conversion/key-event vs CRM lead disagreement.
- Ad spend with zero or missing analytics sessions.
- Missing CRM field mapping for CRM-backed manifests.
- Stale evidence reporting through freshness checks.

These checks are warnings, not truth adjudication. They tell the agent where source systems disagree or where context may be unsafe to trust without review.

## Safety Boundary

Reach is read-only by design at this stage. Real connectors should start with minimal scopes, explicit query manifests, explicit date windows, aggregate summaries, freshness timestamps, source links, and audit records.

Write-back actions to CRMs, ads platforms, analytics tools, or customer systems should remain out of scope until they have a separate permission and review model.
