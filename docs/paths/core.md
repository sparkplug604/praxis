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
7. [Relationship Evidence](../modules/core/relationship-evidence.md): how relationship claims become reviewable candidates and accepted graph edges.

## What Success Looks Like

Core search should return explained results with source context:

```text
priority_breakdown: trust=0.745; freshness=1.000; status=1.000; conflict_penalty=0.000
priority_reasons: relevance:...; trust:...; freshness:fresh(...); graph:...; status:...; conflicts:none
source_id: src:stackoverflow-dev-survey-ai-tooling-mini
capture_id: cap:src-stackoverflow-dev-survey-ai-tooling-mini:...
```

## Current Boundary

Core works locally for capture, ingest, chunking, local embeddings, hybrid search, graph changes, conflict handling, rollback, and skill/reference export.

It is not a hosted multi-user knowledge service, and it does not replace a vector database, knowledge graph, or agent runtime.
