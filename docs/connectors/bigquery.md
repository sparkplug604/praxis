# BigQuery Connector

The BigQuery connector is a read-only Praxis Reach connector for warehouse-backed GTM evidence.

It lets a client capsule point Praxis at a BigQuery project and dataset, run approved aggregate query manifests, and store source-linked evidence cards without copying the client warehouse into Praxis.

## What It Does

- Uses client capsule project, dataset, table, cost, and credential references.
- Uses the official `google-cloud-bigquery` package through a small `BigQueryClient` wrapper.
- Runs a dry run before each query to estimate bytes processed.
- Enforces `max_bytes_billed` from the client capsule.
- Uses generated query templates for approved Reach manifests.
- Supports table allowlists to reduce accidental warehouse access.
- Produces aggregate evidence for segment size, suppression hygiene, buyer-signal rollups, and campaign outcomes.
- Stores query hashes, job metadata, source links, warnings, row counts, and aggregate summaries.
- Leaves raw contact, account, and event rows inside BigQuery by default.

## Install

```bash
python3 -m pip install "praxis-ktos[bigquery]"
```

## Environment

Client capsules store environment variable names. They do not store credentials.

For a client named `acme`, Praxis generates:

```bash
export BIGQUERY_ACME_PROJECT_ID="client-prod"
export BIGQUERY_ACME_DATASET="gtm_mart"
export BIGQUERY_ACME_CREDENTIALS_FILE="/path/to/service-account.json"
```

If no client-specific values are present, the connector can fall back to:

```bash
export BIGQUERY_PROJECT_ID="client-prod"
export BIGQUERY_DATASET="gtm_mart"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

If `GOOGLE_APPLICATION_CREDENTIALS` is not set, live calls may still work when Application Default Credentials are configured in the local environment.

## Client Capsule

Create a client with BigQuery as the warehouse provider:

```bash
praxis reach init
praxis agency client create acme --crm mock_crm --ads mock_ads --warehouse bigquery
```

The generated `systems.json` includes a `warehouse` block like this:

```json
{
  "provider": "bigquery",
  "project_id_env": "BIGQUERY_ACME_PROJECT_ID",
  "dataset_env": "BIGQUERY_ACME_DATASET",
  "credentials_file_env": "BIGQUERY_ACME_CREDENTIALS_FILE",
  "contacts_table": "contacts",
  "buyer_signals_table": "buyer_signals",
  "allowed_tables": [
    "contacts",
    "accounts",
    "campaigns",
    "opportunities",
    "buyer_signals",
    "campaign_outcomes"
  ],
  "max_bytes_billed": 1000000000
}
```

Use table names from the configured dataset, or fully qualified `project.dataset.table` names when needed. Keep `allowed_tables` narrow.

## Commands

```bash
praxis reach connectors list
praxis reach connectors inspect bigquery
praxis reach connectors test bigquery --client acme
praxis reach connectors test bigquery --client acme --live
praxis reach connectors discover bigquery --client acme
praxis reach connectors discover bigquery --client acme --live
praxis reach query run warehouse_segment_size_preview --client acme
praxis reach query run warehouse_buyer_signal_rollup --client acme --days 30
praxis reach evidence show "ev:..."
```

`praxis reach connectors test bigquery --client acme` is a static check. It verifies local configuration only and does not call BigQuery.

`praxis reach connectors test bigquery --client acme --live` runs a tiny dry-run query to verify credentials and query-job access.

`praxis reach connectors discover bigquery --client acme --live` lists tables in the configured dataset. Set `discover_columns` in the warehouse system config when column discovery is needed.

## Current Manifests

The connector currently supports:

- `warehouse_segment_size_preview`: counts contacts, accounts, segment size, suppressed records, missing emails, and stale records when configured.
- `warehouse_buyer_signal_rollup`: counts buyer signals and average signal strength over a date range.
- `warehouse_suppression_check`: checks aggregate suppression and missing-email counts before activation.
- `warehouse_campaign_outcome_rollup`: rolls up campaign outcomes for segment feedback loops.

## Safety Notes

- The connector is read-only.
- Queries are generated from approved Reach manifests.
- BigQuery dry runs happen before execution.
- `max_bytes_billed` should stay configured per client.
- Praxis stores aggregate evidence by default, not raw warehouse rows.
- Keep service account files and credentials outside Praxis files.
- Treat warehouse data as source evidence; use evidence cards and context packs instead of dumping whole tables into prompts.
