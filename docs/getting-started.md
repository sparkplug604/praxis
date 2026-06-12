# Getting Started With Praxis

Praxis turns source material into searchable agent knowledge, traceable evidence, and reusable skill-supporting files.

The fastest way to start is the guided setup wizard:

```bash
praxis setup
```

If you want to see a module in action instead of choosing setup options, run a demo:

```bash
praxis demo core
praxis demo reach
praxis demo agency
```

If the `praxis` command is not on your PATH, use:

```bash
python3 -m praxis setup
```

On Windows PowerShell, use:

```powershell
py -m praxis setup
```

## Pick A Path

The setup wizard offers several first-run paths:

| Path | Use It When You Want To |
| --- | --- |
| `core` | Initialize the local Praxis knowledge layer and ingest/search your first source. |
| `reach-demo` | Try GTM evidence cards and context packs with fixture data and no credentials. |
| `agency-demo` | Run one workflow across two fixture clients. |
| `hubspot` | See the live HubSpot setup checklist without making API calls. |
| `google-ads` | See the live Google Ads setup checklist without making API calls. |
| `ga4` | See the live Google Analytics setup checklist without making API calls. |

For scripted setup, pass the path directly:

```bash
praxis setup --non-interactive --path reach-demo
```

The demo command is more opinionated than setup. It runs a small happy path and prints what happened after each module flow:

| Demo | What It Shows |
| --- | --- |
| `praxis demo core` | A local source becoming captured evidence, graph memory, chunks, embeddings, and explained search results. |
| `praxis demo reach` | Fixture GTM data becoming an evidence card and context pack. |
| `praxis demo agency` | Two fixture clients running the same GTM workflow with separate evidence and context. |

Expected success output:

```text
Reach demo is ready.

You now have:
  - a fixture client capsule: demo
  - local fixture CRM/ad data
  - one Reach evidence card
  - one generated context pack
```

## First Wins

Start with one of these:

```bash
praxis ingest "https://example.com/source"
praxis search "what did this source teach us?" --explain
```

```bash
praxis setup --non-interactive --path reach-demo
praxis reach evidence list --client demo
```

```bash
praxis setup --non-interactive --path agency-demo
praxis agency stale-context-report --all
```

## What Success Looks Like

Core search should return scored results with source context:

```text
score: 0.82 priority: 0.78 source: cap:...
why: semantic match, keyword match, active graph node, no open conflicts
```

Reach evidence should return an evidence id:

```text
evidence_id: ev:demo:weekly_gtm_review:...
storage_level: aggregate_summary
data_quality_status: usable
```

Agency runs should show each client separately:

```text
client_id: acme
status: ok
context_pack: /path/to/workspace/reach/context_packs/...
```

## Next Docs

Paths:

- [Docs index](README.md)
- [Core Path](paths/core.md)
- [Reach Path](paths/reach.md)
- [Agency Path](paths/agency.md)

Module docs:

- [Praxis Core](modules/core/README.md)
- [Praxis Reach](modules/reach/README.md)
- [Praxis Reach for Agencies](modules/agency/README.md)
- [Agency GTM Evaluation Guide](modules/agency/evaluation.md)

Tutorials:

- [Core: ingest and search your first source](tutorials/core/first-source.md)
- [Reach: run the fixture GTM demo](tutorials/reach/fixture-demo.md)
- [Agency: run a multi-client fixture demo](tutorials/agency/fixture-demo.md)

Support:

- [Troubleshooting](troubleshooting.md)
