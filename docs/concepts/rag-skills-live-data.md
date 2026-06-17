# How Praxis Relates To RAG, Skills, And Live Data

Praxis does not replace RAG, vector databases, knowledge graphs, memory systems, agent skills, BI tools, CRMs, ads platforms, analytics tools, or warehouses.

It connects the parts agents need during real work: source material, provisional knowledge, searchable retrieval, graph relationships, operational evidence, client context, and reusable agent instructions.

## The Short Version

RAG helps an agent find information. Skills help an agent repeat useful behavior. Live business systems hold operational truth.

Praxis manages the path between those layers so agents can use knowledge without turning every source into loose prompt context.

| System | What It Gives An Agent | What It Does Not Usually Handle | Where Praxis Fits |
| --- | --- | --- | --- |
| RAG | Relevant text from documents at task time. | Whether the source is trusted, current, logged, conflicted, rollbackable, or reusable outside the current task. | Core captures sources, preserves evidence, indexes chunks, ranks context, and makes retrieved knowledge part of an audited workflow. |
| Vector database | Semantic search over embedded chunks. | Source provenance, graph relationships, skill export, rollback, conflict handling, or agent workflow design. | Core uses vector search as one layer beside keyword search, SkillGraph links, priority scoring, and audit records. |
| Knowledge graph | Relationships between sources, concepts, claims, practices, risks, and tools. | Turning those relationships into task-time retrieval and reusable agent instructions. | Core uses a SkillGraph to make relationships searchable, inspectable, and exportable. |
| Agent memory | Stored facts, lessons, preferences, or prior work across sessions. | Evidence quality, staleness, change history, conflict handling, rollback, and source traceability. | Core treats memory as source-linked, confidence-tagged, reversible knowledge rather than loose remembered text. |
| Agent skills | Reusable instructions, workflows, references, or tool patterns. | Where the knowledge came from, how it changed, and how it should be updated. | Core exports selected knowledge into `SKILL.md`-style artifacts with references and supporting context. |
| BI / dashboards | Metrics and reporting for humans. | Agent-ready context packs, source-linked evidence cards, and reusable query contracts. | Reach turns approved operational queries into compact evidence an agent can use. |
| CRM / ads / analytics systems | Systems of record for customer, campaign, and performance data. | Safe agent context, cross-system warnings, freshness metadata, and local rollbackable evidence artifacts. | Reach queries systems read-only and stores evidence, not a shadow copy. |
| Agency operating workflows | Repeatable client work across many accounts. | Per-client agent context, field maps, permissions, lifecycle state, and consistent query manifests. | Reach for Agencies gives each client a capsule and runs shared workflows through client-specific context. |

## What Praxis Adds

Praxis turns scattered knowledge, source-linked evidence, and client-specific context into reusable agent capability.

| Input | Praxis Layer | Output | Used For |
| --- | --- | --- | --- |
| Documents, research, notes, files, and web sources | **Praxis Core** | Searchable knowledge, SkillGraph links, conflict logs, and reusable skill references | Agent work that needs source-traceable knowledge instead of one-off prompt context |
| CRM, ads, analytics, and other operational systems | **Praxis Reach** | Evidence cards, freshness metadata, GTM warnings, and compact context packs | Agent work that needs live business context without copying the source system |
| Client capsules with systems, field maps, metrics, permissions, and lifecycle state | **Reach for Agencies** | Client-specific evidence, context packs, and repeatable workflows | Agency work across multiple clients with different stacks and data rules |

## Current Boundary

Praxis is local-first and early-stage. Core works locally today. Reach and Reach for Agencies currently provide fixture-friendly and experimental surfaces for source-linked operational evidence and client workflows.

Praxis is not a hosted service, not a CRM, not an analytics warehouse, and not a full autonomous agent runtime.

## Read Next

- [Praxis With LangChain, LangSmith, And Langflow](../integrations/langchain-langsmith-langflow.md)
- [How Praxis Core Is Different](../modules/core/how-core-is-different.md)
- [Retrieval Pipeline](../modules/core/retrieval-pipeline.md)
- [Trust, Traceability, And Rollback](trust-traceability-rollback.md)
