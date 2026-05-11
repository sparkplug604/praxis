# SkillGraph Research Pipeline

This folder is the semi-automatic research lifecycle for evolving the local SkillGraph.

The governing rule is:

```text
internet/source -> capture -> proposal -> review -> graph
```

Nothing from the web should mutate durable graph memory directly.

## Folders

- `inbox/`: manually dropped source notes or future queued research tasks.
- `captures/`: raw and summarized source captures with content hashes.
- `proposals/`: graph update proposals that need review before applying.
- `applied/`: archived copies of proposals that were applied.
- `rejected/`: proposals rejected or deferred after review.

## Commands

Capture one source:

```bash
python3.12 "../scripts/research_source.py" "https://example.com/source"
```

Create a graph update proposal from a capture:

```bash
python3.12 "../scripts/propose_graph_update.py" "cap:source-id:hash"
```

Dry-run an apply:

```bash
python3.12 "../scripts/apply_graph_update.py" "proposals/proposal.json" --dry-run
```

Apply after review:

```bash
python3.12 "../scripts/apply_graph_update.py" "proposals/proposal.json" --review-notes "Checked source evidence."
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

Keyword-derived edges are intentionally conservative and use `relates_to` by default.
Upgrade an edge to `implements`, `mitigates`, `supports`, or `conflicts_with` only when the source evidence really supports that stronger relation.

Watchlist hits are intentionally not graph memory. Treat them as leads until a specific hit is captured, summarized, proposed, reviewed, and applied.

Use high confidence only when at least two of these are true:

- Official docs or primary paper support the claim.
- Source code was inspected.
- Tests or examples ran locally.
- Release/version metadata was verified.
- The claim is narrow and directly evidenced.
