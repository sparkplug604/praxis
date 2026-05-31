# Praxis Reach For Agencies

Praxis Reach for Agencies is the multi-client layer on top of Praxis Reach.

The agency problem is different from the single-company problem. Agencies manage many clients, and each client may use a different CRM, ads stack, analytics setup, field naming scheme, attribution model, timezone, currency, and definition of pipeline.

The goal is not to force every client into the same database. The goal is to let one agency run reusable GTM workflows across different client stacks without losing source-of-truth boundaries.

## Core Idea

Each client gets a **client capsule**.

A client capsule describes:

- who the client is;
- which systems they use;
- which system owns which truth;
- how fields map into canonical GTM objects;
- which metrics matter;
- what data can be stored;
- what must stay in the source system;
- which query manifests and workflows apply.

## First Run

No live credentials required:

```bash
praxis demo agency
```

Then inspect what was created:

```bash
praxis agency client list
praxis agency client show acme
praxis reach evidence list --client acme
praxis agency stale-context-report --all
```

## What The Demo Proves

The fixture demo proves the operating model:

- per-client capsules;
- different client profiles;
- reusable GTM query workflows;
- per-client evidence cards;
- per-client context packs;
- freshness reporting;
- local artifact boundaries.

It does not prove live production extraction across every CRM, ads platform, or analytics tool. Live connectors are separate and currently experimental.

## Client Capsule Shape

The generated capsule lives in:

```text
agency/clients/<client-id>/
  client.json
  systems.json
  field_map.json
  metrics.json
  permissions.json
```

Example:

```json
{
  "client": {
    "id": "acme",
    "name": "Acme SaaS",
    "timezone": "UTC",
    "currency": "USD"
  },
  "permissions": {
    "mode": "read_only",
    "pii_storage": "none",
    "aggregate_cache": "allowed",
    "row_cache": "disallowed",
    "freshness_sla_hours": 24,
    "writeback": "disabled"
  }
}
```

`systems.json`, `field_map.json`, and `metrics.json` hold the stack-specific configuration that lets the same GTM query run across clients with different field names, funnel definitions, and systems.

## Current Connector Status

| Connector | Status |
| --- | --- |
| `fixture_crm` / `fixture_ads` | Works now for demos. |
| `mock_crm` / `mock_ads` | Works now for local testing. |
| `hubspot` | Experimental real connector. |
| `google_ads` | Experimental real connector. |
| `google_analytics` | Experimental real connector for GA4. |

Future connectors can be added by implementing the Reach connector interface and mapping source fields into canonical GTM objects.

## Common Agency Commands

| Command | What It Does |
| --- | --- |
| `praxis agency client create` | Creates a client capsule. |
| `praxis agency client list` | Lists client capsules. |
| `praxis agency client show` | Shows client capsule details. |
| `praxis agency client doctor` | Validates one client capsule. |
| `praxis agency client map-fields` | Shows or updates field mappings. |
| `praxis agency client metrics` | Lists client metric definitions. |
| `praxis agency client define-metric` | Adds or updates a client metric definition. |
| `praxis agency client define-conversion` | Maps source conversion events to canonical metrics. |
| `praxis agency fixture create` | Creates a demo client with fixture CRM/ad data. |
| `praxis agency run` | Runs a Reach workflow across one or many clients. |
| `praxis agency stale-context-report` | Shows which client context is fresh, stale, or missing. |
| `praxis agency client archive` | Archives a client capsule. |
| `praxis agency client export` | Exports client artifacts. |
| `praxis agency client delete-plan` | Creates a guarded deletion plan. |
| `praxis agency client delete` | Deletes client artifacts after exact confirmation. |
| `praxis agency client purge` | Permanently purges quarantined artifacts after exact confirmation. |

## Field Maps And Metrics

Agencies can inspect or update a client's field map from the CLI:

```bash
praxis agency client map-fields acme
praxis agency client map-fields acme --object opportunity --field amount --source-field properties.amount
```

Client-specific metric definitions can also be updated:

```bash
praxis agency client metrics acme
praxis agency client define-metric acme mqls \
  --canonical-object contact \
  --description "Marketing qualified leads" \
  --source-priority crm \
  --definition "lifecycle_stage == marketingqualifiedlead"
```

This is what lets the same agency workflow run across clients with different field names and funnel definitions.

## Multi-Client Runs

Agency runs can target a list of clients or every active client capsule:

```bash
praxis agency run weekly_gtm_review --clients acme,beta --days 90
praxis agency run weekly_gtm_review --all-clients --context
```

By default, a failing client stops the run. For agency operations, `--continue-on-error` lets the run keep going and print a client-by-client report:

```bash
praxis agency run weekly_gtm_review --all-clients --context --continue-on-error
```

This is useful when one client has a missing credential or broken connector but the rest of the book of business should still produce evidence cards and context packs.

Archived clients are skipped from default `--all-clients` runs. If an archived client is selected explicitly, Praxis refuses the run until the capsule is restored or recreated.

## Client Lifecycle

Client capsules need a safe offboarding path because Reach can create local evidence cards, context packs, fixture files, and Core captures derived from client work.

The lifecycle flow is intentionally staged:

```bash
praxis agency client archive acme --reason "contract ended"
praxis agency client export acme
praxis agency client delete-plan acme --reason "privacy request"
praxis agency client delete --plan "del:..." --confirm-client acme --confirm-delete DELETE
praxis agency client purge --receipt "receipt:..." --confirm-delete PURGE
```

`archive` marks the client inactive and removes it from normal agency runs.

`export` writes a redacted `.tar.gz` bundle containing the client capsule and local Reach artifacts.

`delete-plan` discovers the local artifacts that belong to the client and writes a reviewed plan.

`delete` requires the saved plan id, exact client id confirmation, and `DELETE`. It moves local files into lifecycle quarantine, removes matching Reach-derived source/vector records from local databases, and writes a deletion receipt.

`purge` requires the deletion receipt and `PURGE`. It permanently removes the quarantine folder.

Praxis deletion only affects local Praxis artifacts. It does not delete records inside CRMs, ad platforms, analytics tools, or other source systems.

## Product Boundary

Praxis Core is the knowledge layer.

Praxis Reach is the live operational evidence layer.

Praxis Reach for Agencies is the multi-client operating layer that lets an agency run the same GTM playbook across different client stacks.
