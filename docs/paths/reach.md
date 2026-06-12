# Reach Path

Use this path when you want agents to work from source-linked GTM evidence without cloning live operational systems into Praxis.

## Start Here

Run the Reach demo:

```bash
praxis demo reach
```

If `praxis` is not on your PATH:

```bash
python3 -m praxis demo reach
```

## What To Read Next

1. [Praxis Reach](../modules/reach/README.md): what Reach stores and the main commands.
2. [Reach fixture demo](../tutorials/reach-fixture-demo.md): inspect fixture evidence and build a context pack.
3. [Connector docs](../README.md#connectors): review current connector setup notes.
4. [Troubleshooting](../troubleshooting.md): diagnose credentials, search, setup, or ingest issues.

## What Success Looks Like

Reach evidence should return an evidence id:

```text
evidence_id: ev:demo:weekly_gtm_review:...
storage_level: aggregate_summary
data_quality_status: usable
```

## Current Boundary

Reach works locally with fixture and mock connectors. HubSpot, Google Ads, Google Analytics, and BigQuery support are experimental real connector surfaces.

Reach is read-only by design at this stage. It stores evidence cards and context packs, not full copies of source systems.
