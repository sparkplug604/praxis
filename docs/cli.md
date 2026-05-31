# Praxis CLI

Praxis exposes one package command:

```bash
praxis --help
praxis <command> --help
```

New users can start with the guided setup wizard:

```bash
praxis setup
praxis setup --non-interactive --path reach-demo
```

Or run a module demo:

```bash
praxis demo
praxis demo core
praxis demo reach
praxis demo agency
```

If the `praxis` command is not on PATH, use Python's module form:

```bash
python3 -m praxis --help
python3 -m praxis <command> --help
```

On Windows PowerShell:

```powershell
py -m praxis --help
py -m praxis <command> --help
```

Praxis is currently checkout/workspace-oriented. The CLI expects a Praxis root containing `scripts/`, `db/`, `kg/`, `research/`, and `vectors/`.

If you run the CLI outside the checkout, pass `--root /path/to/Praxis` or set `PRAXIS_ROOT`.

Important: `ingest`, `search`, `graph`, and other actions are Praxis subcommands. Run `praxis ingest "https://example.com/source"` or `py -m praxis ingest "https://example.com/source"`, not `ingest "https://example.com/source"` by itself.

## Reach And Agency Commands

Praxis Reach and Praxis Reach for Agencies are experimental modules for live operational context and multi-client GTM workflows.

```bash
praxis reach init
praxis reach doctor
praxis reach connectors list
praxis reach connectors inspect hubspot
praxis reach connectors test hubspot --client acme
praxis reach connectors test hubspot --client acme --live
praxis reach connectors test google_ads --client acme
praxis reach connectors test google_analytics --client acme
praxis reach connectors discover google_ads --client acme --live
praxis reach connectors discover google_analytics --client acme --live
praxis reach query list
praxis reach query run weekly_gtm_review --client acme --days 90
praxis reach query run website_performance --client acme --days 30
praxis reach query run traffic_attribution_check --client acme --days 30
praxis reach query run full_gtm_signal_check --client acme --days 30
praxis reach query run weekly_gtm_review --client acme --start-date 2026-01-01 --end-date 2026-01-31
praxis reach evidence list --client acme
praxis reach evidence show "ev:..."
praxis reach evidence refresh "ev:..."
praxis reach evidence capture "ev:..."
praxis reach stale list --client acme
praxis reach context build weekly_gtm_review --client acme

praxis agency client create acme --name "Acme SaaS" --crm hubspot --ads google_ads --analytics google_analytics
praxis agency client list
praxis agency client show acme
praxis agency client doctor acme
praxis agency client map-fields acme
praxis agency client metrics acme
praxis agency client define-metric acme mqls --canonical-object contact --description "Marketing qualified leads" --definition "lifecycle_stage == marketingqualifiedlead"
praxis agency client define-conversion acme lead_form --source google_ads --source-name "Lead Form Submit" --canonical-metric conversions
praxis agency client define-conversion acme ga4_lead --source google_analytics --source-name generate_lead --canonical-metric conversions
praxis agency client archive acme --reason "contract ended"
praxis agency client export acme
praxis agency client delete-plan acme --reason "privacy request"
praxis agency client show-delete-plan "del:..."
praxis agency client delete --plan "del:..." --confirm-client acme --confirm-delete DELETE
praxis agency client purge --receipt "receipt:..." --confirm-delete PURGE
praxis agency fixture create demo --profile b2b-saas
praxis agency run weekly_gtm_review --all-clients --context
praxis agency run weekly_gtm_review --all-clients --context --continue-on-error
praxis agency run weekly_gtm_review --clients acme,beta --start-date 2026-01-01 --end-date 2026-01-31
praxis agency stale-context-report
```

Reach currently ships with `mock_crm`, `mock_ads`, `fixture_crm`, and `fixture_ads` so the zero-copy evidence-card flow can be tested without live credentials. Experimental `hubspot`, `google_ads`, and `google_analytics` connector classes are present but require credentials and read-only setup.

## Common Commands

Run guided setup:

```bash
praxis setup
praxis setup --non-interactive --path core
praxis setup --non-interactive --path reach-demo
praxis setup --non-interactive --path agency-demo
```

Run demos:

```bash
praxis demo
praxis demo core
praxis demo reach
praxis demo agency
```

Initialize and check a checkout:

```bash
praxis bootstrap
praxis doctor --require-index
praxis eval
```

Search the corpus and SkillGraph:

```bash
praxis search "knowledge to skill loop"
praxis search "knowledge to skill loop" --explain
praxis search "knowledge to skill loop" --rank-by relevance
praxis graph search "SkillGraph"
```

`praxis search` ranks by unified context priority by default. The priority score keeps retrieval relevance visible, then adjusts for source trust, freshness, graph fit, live/deprecated status, and unresolved conflicts. Use `--rank-by relevance` when you want the raw retrieval order without those governance signals.

Capture a source and auto-apply provisional graph memory:

```bash
praxis ingest "https://example.com/source"
```

Windows/PATH-safe form:

```powershell
py -m praxis ingest "https://example.com/source"
```

Inspect or rollback graph changes:

```bash
praxis changes list
praxis changes show "chg:..."
praxis promote "chg:..."
praxis deprecate "chg:..."
praxis rollback "chg:..."
praxis rollback "chg:..." --force
```

Inspect and resolve conflict/dedupe records:

```bash
praxis conflicts list
praxis conflicts show "conflict:..."
praxis conflicts resolve "conflict:..." --resolution "keep_both_with_scope" --notes "Different scopes."
praxis dedupe list
praxis dedupe show "conflict:duplicate_entity:..."
praxis dedupe merge "conflict:duplicate_entity:..." --canonical "node:id"
praxis dedupe split "chg:..."
```

Refresh retrieval indexes:

```bash
praxis chunk --changed-only
praxis chunk --changed-only --chunk-strategy auto
praxis chunk --changed-only --chunk-strategy legacy
praxis embed --provider local-hash
```

`praxis chunk` defaults to `--chunk-strategy auto`, which detects Markdown, code, JSON, and plain text. Auto chunking preserves structural boundaries where possible and stores chunk metadata such as parent context, block types, boundary rationale, and overlap context. Use `--chunk-strategy legacy` if you want the original paragraph-block chunker.

Export with conflict safety:

```bash
praxis export-graph --include-conflict-notes
praxis export-graph --fail-on-open-conflicts
praxis export-skill-refs --fail-on-open-conflicts
praxis export-skill-refs --include-conflict-notes
```

## Script Wrappers

The `scripts/` folder contains compatibility wrappers around the packaged CLI. They are useful when running from a checkout without installing the package.

```bash
python3 scripts/hybrid_search.py "test-backed refactoring"
python3 scripts/search_skill_graph.py search "refactoring"
python3 scripts/ingest_source.py "https://example.com/source"
python3 scripts/conflicts.py list
python3 scripts/dedupe.py list
python3 scripts/graph_changes.py list
python3 scripts/promote_graph_change.py "chg:..."
python3 scripts/deprecate_graph_change.py "chg:..."
python3 scripts/rollback_graph_change.py "chg:..."
python3 scripts/research_source.py "https://example.com/source"
python3 scripts/propose_graph_update.py "cap:source-id:hash"
python3 scripts/apply_graph_update.py "research/proposals/proposal.json" --dry-run
python3 scripts/chunk_sources.py --changed-only
python3 scripts/index_vectors.py --provider local-hash
python3 scripts/eval_retrieval.py
python3 scripts/skill_doctor.py
python3 scripts/setup.py
python3 scripts/demo.py
```
