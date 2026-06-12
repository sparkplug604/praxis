# Core Path

Use this path when you want Praxis to turn source material into searchable, source-traceable agent knowledge.

## Start Here

Run the Core demo:

```bash
praxis demo core
```

If `praxis` is not on your PATH:

```bash
python3 -m praxis demo core
```

## What To Read Next

1. [Praxis Core](../modules/core/README.md): what Core does and the main commands.
2. [Core first source tutorial](../tutorials/core-first-source.md): ingest and search one source.
3. [Praxis Intake](../modules/core/intake.md): how source detection and conversion work.
4. [Praxis Authority Anchors](../modules/core/authority.md): how source-of-record rules are represented.
5. [Praxis Core Governance](../modules/core/governance.md): how evidence reuse, receipts, and warnings work.

## What Success Looks Like

Core search should return scored results with source context:

```text
score: 0.82 priority: 0.78 source: cap:...
why: semantic match, keyword match, active graph node, no open conflicts
```

## Current Boundary

Core works locally for capture, ingest, chunking, local embeddings, hybrid search, graph changes, conflict handling, rollback, and skill/reference export.

It is not a hosted multi-user knowledge service, and it does not replace a vector database, knowledge graph, or agent runtime.
