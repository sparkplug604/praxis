# Praxis Authority Anchors

Praxis Authority Anchors are an experimental Core feature for deciding which sources are allowed to settle different kinds of claims.

The CLI is `praxis authority`. Core governance uses these authority rules through `praxis governance`.

## What This Solves

RAG systems often keep evidence, chunks, summaries, and graph memory, but still need a separate rule for source authority.

For example:

- a CRM should be the authority for pipeline stage;
- Google Ads may be useful context for ad spend, but not the authority for closed revenue;
- an LLM summary should not override a live system of record;
- stale operational data should be warned on instead of silently treated as current truth.

Authority Anchors make those rules inspectable and testable.

## What It Does Today

The first implementation supports:

- a `workspace/authority/` runtime folder;
- JSON authority bundles;
- a compiled local SQLite authority registry;
- source-of-record anchors by claim type, client, and metadata scope;
- freshness checks;
- forbidden source checks;
- required evidence checks;
- append-only adjudication records.

This is not a complete policy engine yet. It is the first practical anchor point for source authority.

## Basic Flow

```bash
praxis authority init
praxis authority activate workspace/authority/bundles/client.json
praxis authority compile
praxis authority verify --strict
praxis authority anchors list
```

Adjudicate a claim source:

```bash
praxis authority adjudicate \
  --claim-type operational_metric \
  --source system_of_record \
  --evidence "ev:example" \
  --fresh-at "2026-06-10T12:00:00+00:00"
```

Inspect adjudication records:

```bash
praxis authority records list
praxis authority records show "adjudication:..."
```

## Bundle Shape

Generated authority bundles live in `workspace/authority/bundles/`.

```json
{
  "bundle_id": "bundle:client",
  "version": 1,
  "anchors": [
    {
      "id": "anchor:client:hubspot_pipeline",
      "scope": {
        "claim_type": "pipeline_metric",
        "client_id": "acme"
      },
      "authoritative_source": "hubspot",
      "fallback_sources": ["evidence_card"],
      "forbidden_sources": ["google_ads", "llm_summary"],
      "freshness_sla_hours": 12,
      "conflict_behavior": "block_on_conflict",
      "required_evidence": ["evidence_id"],
      "safe_default": "ask_for_hubspot_export"
    }
  ]
}
```

Use `praxis authority activate <bundle.json>` to make a bundle active, then run `praxis authority compile`.

## Current Decisions

`praxis authority adjudicate` can return:

| Decision | Meaning |
| --- | --- |
| `allow` | The source matches the authority anchor and the evidence is fresh enough. |
| `warn` | The source may be usable, but it is stale or fallback-only. |
| `block` | The source is forbidden, missing required evidence, or not authoritative for a blocking anchor. |
| `unknown` | No matching authority anchor exists yet. |

## Why This Matters For Reach

Praxis Reach creates evidence cards from live operational systems. Authority Anchors define which system should win when operational sources disagree.

Example:

- HubSpot is the authority for opportunity stage.
- Google Ads is the authority for campaign spend.
- GA4 is the authority for website sessions.
- BigQuery may be the authority for warehouse-mode joined metrics.

Those rules should live outside prompts so agents do not improvise them during retrieval.

## What It Does Not Do Yet

Authority Anchors are not yet wired into every Core and Reach command, but the first Core governance hooks now exist.

Future work:

- use authority checks during `praxis ingest`;
- deepen authority warnings in `praxis search --explain`;
- add more granular export policies beyond strict health checks;
- connect authority decisions to first-class decision trails;
- support signed bundles and stronger tamper-evidence for adversarial environments.
