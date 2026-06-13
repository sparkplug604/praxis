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
2. [How Praxis Core Is Different](../modules/core/how-core-is-different.md): why Core is more than plain chunk-and-vector retrieval.
3. [Core first source tutorial](../tutorials/core/first-source.md): ingest and search one source.
4. [Ingestion Pipeline](../modules/core/ingestion-pipeline.md): how sources become captures, chunks, embeddings, and entity-aware evidence.
5. [Retrieval Pipeline](../modules/core/retrieval-pipeline.md): how search ranks context using vector, keyword, graph, entity, trust, freshness, status, and conflict signals.
6. [Entity-Aware Evidence](../modules/core/entity-aware-evidence.md): how mentions become evidence annotations such as `ann:...`.

## What Success Looks Like

Core search should return scored results with source context:

```text
score: 0.82 priority: 0.78 source: cap:...
why: semantic match, keyword match, active graph node, no open conflicts
```

## Current Boundary

Core works locally for capture, ingest, chunking, local embeddings, hybrid search, graph changes, conflict handling, rollback, and skill/reference export.

It is not a hosted multi-user knowledge service, and it does not replace a vector database, knowledge graph, or agent runtime.
