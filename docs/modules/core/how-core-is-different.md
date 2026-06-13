# How Praxis Core Is Different

Use this page when you want the short technical answer to: "What is Praxis Core doing that a typical RAG app is not?"

Run the fastest Core demo first:

```bash
praxis demo core
```

## Short Version

Praxis Core is a local, source-traceable knowledge layer for agents.

It does not only chunk documents and run vector search. Core keeps track of how sources entered the system, how chunks were created, which graph objects changed, which conflicts were detected, which entities were resolved, and whether evidence can be reused safely.

## What Typical RAG Usually Has

| Layer | Typical RAG |
| --- | --- |
| Source intake | Load text, often with limited parse-quality metadata. |
| Indexing | Chunk text and create embeddings. |
| Retrieval | Return the nearest chunks for a query. |
| Provenance | Maybe include source filenames or URLs. |
| Updates | Re-index or overwrite stale chunks. |
| Conflicts | Usually handled outside the retrieval system. |
| Agent reuse | Usually handled by prompts or separate tools. |

## What Praxis Core Adds

| Layer | Praxis Core |
| --- | --- |
| Source intake | Detects source type, converts files, preserves converter metadata, and records parse-quality warnings. |
| Source registry | Stores source IDs, capture IDs, content hashes, credibility, freshness windows, raw text, summaries, and metadata. |
| Graph memory | Writes proposed SkillGraph changes as auditable change sets instead of treating extracted knowledge as automatically true. |
| Retrieval | Combines vector hits, keyword hits, SkillGraph hints, optional entity-aware hints, context-priority scoring, and explanation output. |
| Entity evidence | Extracts entity mentions from chunks, resolves them against SkillGraph nodes and aliases, and creates evidence annotations such as `ann:...`. |
| Conflict management | Logs duplicate sources, duplicate content, possible duplicate entities, and claim-like contradictions for review. |
| Hygiene | Supports inspect, promote, deprecate, dedupe, rollback, authority checks, governance checks, and hash-chain receipts. |
| Agent reuse | Exports reviewed knowledge into Markdown references and skill-supporting files. |

## The Important Difference

Praxis treats retrieved context as evidence with history, status, and risk signals.

Search can show why a result appeared:

```bash
praxis search "Acme renewal risk" --entity-aware --explain
```

The explanation can include retrieval scores:

- vector score;
- keyword score;
- graph score;
- entity score.

It can also include provenance and safety signals:

- source ID;
- capture ID;
- intake metadata;
- graph links;
- accepted entity links;
- trust, freshness, status, and conflict penalties.

## Where To Read More

- [Core Architecture](core-architecture.md): how the local system is layered.
- [Ingestion Pipeline](ingestion-pipeline.md): how source material becomes captures, graph proposals, chunks, embeddings, and optional entity evidence.
- [Retrieval Pipeline](retrieval-pipeline.md): how search combines vector, keyword, graph, entity, trust, freshness, status, and conflict signals.
- [Entity-Aware Evidence](entity-aware-evidence.md): how entity mentions become evidence annotations.
- [Maintenance And Hygiene](maintenance-and-hygiene.md): how Core keeps local knowledge inspectable and reversible.
- [Conflicts And Dedupe](conflicts-and-dedupe.md): how Core detects and manages suspicious duplicate or contradictory knowledge.

## Current Boundary

Core works locally for source capture, ingest, chunking, local embeddings, hybrid search, entity-aware evidence annotations, graph changes, conflict records, dedupe, rollback, authority checks, governance checks, and skill/reference export.

Core is not a hosted memory service, not a production vector database, not a full autonomous agent runtime, and not a fully automatic entity knowledge graph. Entity extraction and resolution are useful, but accepted entities still depend on source evidence, SkillGraph aliases, and reviewable statuses.
