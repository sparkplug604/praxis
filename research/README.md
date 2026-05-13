# SkillGraph Research Pipeline

This folder is the research lifecycle for evolving the local SkillGraph.

The governing rule is:

```text
internet/source -> capture -> provisional graph update -> audit log -> inspect/rollback/promote
```

Praxis is automation-first: captured sources can mutate the SkillGraph automatically as provisional, source-linked memory. Every graph mutation should leave an audit trail so the update can be inspected, rolled back, deprecated, or promoted later.

## Folders

- `inbox/`: manually dropped source notes or future queued research tasks.
- `captures/`: raw and summarized source captures with content hashes.
- `proposals/`: inspectable graph update proposals generated from captures.
- `applied/`: archived copies of proposals that were applied manually or automatically.
- `rejected/`: proposals rejected or deferred after review.

## Commands

Capture one source:

```bash
python3.12 "../scripts/research_source.py" "https://example.com/source"
```

Capture and auto-apply a provisional SkillGraph update:

```bash
python3.12 "../scripts/ingest_source.py" "https://example.com/source"
```

Create a graph update proposal from a capture:

```bash
python3.12 "../scripts/propose_graph_update.py" "cap:source-id:hash"
```

Dry-run an apply:

```bash
python3.12 "../scripts/apply_graph_update.py" "proposals/proposal.json" --dry-run
```

Apply manually after inspection:

```bash
python3.12 "../scripts/apply_graph_update.py" "proposals/proposal.json" --review-notes "Checked source evidence."
```

Inspect and rollback graph changes:

```bash
python3.12 "../scripts/graph_changes.py" list
python3.12 "../scripts/graph_changes.py" show "chg:..."
python3.12 "../scripts/rollback_graph_change.py" "chg:..."
```

Check stale sources:

```bash
python3.12 "../scripts/refresh_stale_sources.py" --topic governance
```

Scan frontier watchlists:

```bash
python3.12 "../scripts/scan_watchlist.py" agent_research --limit 25
```

Promote a ranked hit into the capture store:

```bash
python3.12 "../scripts/capture_research_hit.py" --list --watchlist agent_research
python3.12 "../scripts/capture_research_hit.py" "hit:run-agent-research-..."
```

## Review Notes

Keyword-derived edges are intentionally conservative, provisional, and use `relates_to` by default.
Upgrade an edge to `implements`, `mitigates`, `supports`, or `conflicts_with` only when the source evidence really supports that stronger relation.

Watchlist hits are leads until a specific hit is captured. Captured hits may be auto-applied as provisional graph memory, but high-trust skills and policies should still be promoted deliberately.

Use high confidence only when at least two of these are true:

- Official docs or primary paper support the claim.
- Source code was inspected.
- Tests or examples ran locally.
- Release/version metadata was verified.
- The claim is narrow and directly evidenced.
