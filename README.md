# Praxis

Praxis connects retrieval-based knowledge systems with skill-based agent behavior and live operational context.

It is organized into three modules that work together:

- **Praxis Core** turns documents, research, web pages, local files, and project notes into searchable, source-traceable agent knowledge and reusable skill-supporting files.
- **Praxis Reach** lets agents work from live operational evidence, such as CRM, ads, and analytics context, without cloning those source systems into Praxis.
- **Praxis Reach for Agencies** adds per-client capsules so agencies can run repeatable GTM workflows across clients with different systems, metrics, field maps, permissions, and freshness needs.

Together, the modules create a knowledge-to-action loop. Core handles durable agent knowledge. Reach handles source-linked live evidence. Reach for Agencies handles multi-client operating context. The point is not to make another agent runtime. The point is to give agents a maintained knowledge layer they can search, trust, update, roll back, and reuse.

Praxis gives agents a way to build on what they learn without dragging a giant context window behind them. It makes agent knowledge searchable, traceable, reversible, and reusable, so every useful source can become practical agent capability.

## Praxis Modules

| Module | What It Does | Best For | Status |
| --- | --- | --- | --- |
| [**Praxis Core**](docs/modules/core/README.md) | Turns source material into searchable memory, traceable evidence, SkillGraph knowledge, and reusable agent instructions. | RAG, agent memory, research libraries, coding agents, skill systems. | Available |
| [**Praxis Reach**](docs/modules/reach/README.md) | Adds a zero-copy live-data layer for operational systems through read-only connectors, query manifests, evidence cards, and context packs. | Teams that want agents to use CRM, ads, analytics, or operational data without cloning source systems. | Experimental |
| [**Praxis Reach for Agencies**](docs/modules/reach-for-agencies/README.md) | Adds per-client capsules so agencies can run reusable workflows across clients with different stacks, metrics, permissions, and field maps. | Agencies, GTM teams, consultants, multi-client operators. | Experimental |

For agency/GTM evaluation, start with the [Agency GTM Evaluation Guide](docs/evaluators/agency-gtm-evaluation.md).

## Highlights

- **Turn useful sources into agent knowledge**: Core captures links, files, papers, docs, notes, directories, and selected watchlist hits with source metadata preserved.
- **Make agent memory traceable by default**: Core stores raw text, summaries, chunks, hashes, source IDs, confidence, graph links, and audit logs in local SQLite databases.
- **Rank the best context first**: Core search combines semantic matching, keyword matching, SkillGraph links, freshness, trust, status, and conflict signals. `--explain` shows why each result appeared.
- **Move fast without poisoning memory**: Core writes new captures into provisional SkillGraph memory, then lets you inspect, promote, deprecate, dedupe, or roll back changes.
- **Use live evidence without cloning live systems**: Reach creates source-linked evidence cards from read-only query manifests instead of copying whole CRMs, ads accounts, or analytics properties into local memory.
- **Give agents fresh operational context**: Reach turns evidence cards into context packs with source links, freshness metadata, warnings, conflicts, and query provenance.
- **Run repeatable workflows across clients**: Reach for Agencies uses client capsules to keep each client's systems, fields, metrics, permissions, and lifecycle state separate.
- **Turn knowledge into reusable agent instructions**: Praxis can export selected database and SkillGraph material into Markdown references and `SKILL.md`-style supporting files for agent runtimes.
- **Own the knowledge layer**: Praxis runs with SQLite, scripts, local-hash embeddings, and optional external embeddings from a normal checkout, without locking into one hosted service, model, or agent runtime.

## Who This Is For

Praxis is for builders who are tired of agents starting from zero.

Every project teaches you something: a better workflow, a useful paper, a hard-won debugging lesson, a design decision, a prompt pattern, a failure mode, a customer insight, a metric definition. Most of that knowledge disappears into chat history, random docs, oversized skill files, or dashboards an agent cannot safely query.

Praxis gives that knowledge somewhere to go.

**Use Praxis Core if you:**

- build coding agents, research agents, support agents, ops agents, or internal AI tools that need durable knowledge;
- collect docs, papers, web pages, project notes, examples, SOPs, and decisions faster than you can organize them;
- want RAG that is more than a pile of chunks: source-backed, searchable, explainable, and connected to graph memory;
- want skills and agent instructions that stay focused instead of becoming giant always-on prompt files;
- need memory that can update quickly without becoming an untraceable junk drawer.

**Use Praxis Reach if you:**

- need agents to answer operational questions from CRM, ads, analytics, or other source systems;
- do not want to clone live business systems into a local database just to give an agent context;
- need evidence cards with source links, timestamps, freshness checks, and conflict warnings;
- want agents to use live data through approved query manifests instead of free-form data pulls.

**Use Praxis Reach for Agencies if you:**

- manage multiple clients with different stacks, field names, metrics, permissions, and reporting habits;
- want reusable GTM workflows that run per client without flattening every client into the same schema;
- need client capsules that keep systems, field maps, metrics, permissions, evidence, context packs, and lifecycle state separated;
- need archive, export, delete-plan, delete, and purge flows for local client artifacts.

## How Praxis Relates To RAG, Skills, And Live Data

Praxis does not replace RAG, vector databases, knowledge graphs, memory systems, agent skills, BI tools, or CRMs. It connects the parts agents need during real work.

RAG helps an agent find information. Skills help an agent repeat useful behavior. Live business systems hold operational truth. Praxis manages the path between source material, provisional knowledge, searchable retrieval, graph relationships, live evidence, client context, and reusable agent instructions.

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

## What Praxis Does

Praxis turns scattered knowledge, source-linked evidence, and client-specific context into reusable agent capability.

| Input | Praxis Layer | Output | Used For |
| --- | --- | --- | --- |
| Documents, research, notes, files, and web sources | **Praxis Core** | Searchable knowledge, SkillGraph links, conflict logs, and reusable skill references | Agent work that needs source-traceable knowledge instead of one-off prompt context |
| CRM, ads, analytics, and other operational systems | **Praxis Reach** | Evidence cards, freshness metadata, GTM warnings, and compact context packs | Agent work that needs live business context without copying the source system |
| Client capsules with systems, field maps, metrics, permissions, and lifecycle state | **Reach for Agencies** | Client-specific evidence, context packs, and repeatable workflows | Agency work across multiple clients with different stacks and data rules |

| Layer | What It Does |
| --- | --- |
| **Praxis Core** | Captures source material, preserves raw evidence, creates summaries, chunks and embeds content, maps relationships in a SkillGraph, ranks search results, logs conflicts, and exports reusable references or skills. |
| **Praxis Reach** | Runs approved read-only queries through connectors, writes evidence cards with source links and freshness metadata, checks for GTM conflicts, and builds context packs for agent work. |
| **Praxis Reach for Agencies** | Stores per-client capsules with systems, field maps, metrics, permissions, and lifecycle state so the same workflow can run across different client stacks. |

## How Knowledge Moves Through Praxis

Praxis has three related flows.

**Core: source to skill**

| Step | What Happens |
| --- | --- |
| Capture source | Praxis saves the source text, metadata, hashes, and source ID. |
| Archive evidence | Raw and summarized evidence stay attached so claims can be checked later. |
| Create provisional graph memory | New graph knowledge is added quickly, but it remains traceable and reversible. |
| Audit, inspect, or rollback | Change sets show what changed and make bad knowledge easy to unwind. |
| Chunk and embed | Captured material becomes searchable chunks and embeddings. |
| Search with explanations | Results can show why they matched, which source they came from, and whether conflicts exist. |
| Export reusable references or skills | Selected knowledge can become Markdown references or `SKILL.md`-style supporting files. |

**Reach: live system to context pack**

| Step | What Happens |
| --- | --- |
| Source system | The truthful operational data stays in the CRM, ads platform, analytics tool, or other source system. |
| Read-only connector | Praxis queries approved data without writing back to the source system. |
| Query manifest | Each query records the metric, source, filters, time window, and permissions. |
| Evidence card | Results are saved as compact, source-linked evidence with timestamps and freshness metadata. |
| Freshness and conflict checks | Praxis warns when evidence is stale or when sources disagree. |
| Context pack | Evidence is packaged into agent-ready context for a specific job. |
| Agent work | The agent works from compact evidence instead of raw exports or giant prompt dumps. |

**Agency: client capsule to repeatable workflow**

| Step | What Happens |
| --- | --- |
| Client capsule | Each client gets an isolated local capsule. |
| Systems, field maps, metrics, and permissions | The capsule records how that client names fields, defines metrics, and limits access. |
| Reach query | Shared agency workflows run through the client's specific systems and field maps. |
| Client evidence | Results are stored as client-scoped evidence cards. |
| Client context pack | Evidence becomes a compact packet for campaign reviews, diagnostics, or reporting work. |
| Reusable agency workflow | The same workflow can run across clients without pretending every client has the same stack. |

This is the core idea: documents become searchable knowledge, live systems become source-linked evidence, and client-specific context becomes repeatable agent workflow.

## Trust, Traceability, And Rollback

Praxis treats memory as evidence, not truth.

For source knowledge, captured material is stored with source context so claims can be checked later. SkillGraph updates are provisional by default. Every graph mutation is logged as a change set with before/after records, and reverted, merged, or deprecated graph objects are hidden from normal search/export unless you explicitly inspect them.

For live organizational data, Reach is read-only by design at this stage. It stores evidence cards, query metadata, source links, timestamps, freshness checks, aggregate summaries, and warnings. It does not store secrets, does not write back to source systems, and does not try to become a CRM, ads platform, analytics tool, or warehouse.

For client data, Reach for Agencies keeps each client in a separate capsule with its own systems, field maps, metrics, permissions, evidence, context packs, and lifecycle state. Client offboarding is staged through archive, export, delete-plan, delete, quarantine, and purge commands. Local Praxis deletion affects local Praxis artifacts only; it does not delete records inside client systems.

Praxis also keeps a Conflict Ledger. Ingest and promotion can log duplicate sources, duplicate content, possible duplicate entities, and likely claim contradictions. Reach can attach GTM-specific conflict warnings when operational sources disagree. Search can show conflict warnings with `--explain`, exports can refuse unresolved conflicts with `--fail-on-open-conflicts`, and dedupe merges are reversible through audited change sets.

Praxis is built to let agents move quickly without turning memory, live evidence, or client context into an untraceable junk drawer.

## Start Here

Clone and install:

```bash
git clone https://github.com/sparkplug604/praxis.git
cd praxis
python3 -m pip install -e .
```

Windows PowerShell:

```powershell
git clone https://github.com/sparkplug604/praxis.git
cd praxis
py -m pip install -e .
```

Run a demo:

```bash
praxis demo core
praxis demo reach
praxis demo agency
```

If `praxis` is not recognized after installation, use Python's module form:

```bash
python3 -m praxis demo core
python3 -m praxis demo reach
python3 -m praxis demo agency
```

Windows PowerShell:

```powershell
py -m praxis demo core
py -m praxis demo reach
py -m praxis demo agency
```

Pick the first win that matches your use case:

| If You Want To... | Run This | Then Read |
| --- | --- | --- |
| Turn docs/research into searchable agent knowledge. | `praxis demo core` | [Praxis Core](docs/modules/core/README.md) |
| Try live-data-style evidence without credentials. | `praxis demo reach` | [Praxis Reach](docs/modules/reach/README.md) |
| Evaluate the agency / GTM workflow. | `praxis demo agency` | [Agency GTM Evaluation Guide](docs/evaluators/agency-gtm-evaluation.md) |

For guided setup:

```bash
praxis setup
```

More setup help lives in [docs/getting-started.md](docs/getting-started.md). If something fails on Windows, PATH, install, SQLite setup, or credentials, see [docs/troubleshooting.md](docs/troubleshooting.md).

## Praxis CLI

The Praxis core is the Python package and CLI. Use `praxis --help` and `praxis <command> --help` for exact options.

| Command Group | Purpose |
| --- | --- |
| `setup`, `demo`, `doctor`, `eval` | Get started, run module demos, and verify the local workspace. |
| `capture`, `ingest`, `scan`, `refresh` | Bring source material into Praxis. |
| `chunk`, `embed`, `search`, `graph`, `library` | Index and retrieve knowledge. |
| `changes`, `conflicts`, `dedupe`, `rollback` | Inspect, resolve, merge, or undo memory changes. |
| `export-graph`, `export-skill-refs` | Export selected knowledge into references and skill-supporting files. |
| `reach` | Work with operational evidence, query manifests, freshness, and context packs. |
| `agency` | Manage client capsules and multi-client workflows. |

Full command reference: [docs/cli.md](docs/cli.md)

Module docs:

- [Docs Index](docs/README.md)
- [Praxis Core](docs/modules/core/README.md)
- [Praxis Reach](docs/modules/reach/README.md)
- [Praxis Reach for Agencies](docs/modules/reach-for-agencies/README.md)
- [Agency GTM Evaluation Guide](docs/evaluators/agency-gtm-evaluation.md)

## What Works Today

| Area | Status |
| --- | --- |
| Core source capture, ingest, chunking, local embeddings, hybrid search | Works locally |
| SkillGraph changes, conflict ledger, dedupe, rollback | Works locally |
| Skill/reference export | Works locally |
| Reach fixture evidence and context packs | Works locally |
| Agency fixture demo and client capsules | Works locally |
| HubSpot connector | Experimental |
| Google Ads connector | Experimental |
| Google Analytics / GA4 connector | Experimental |
| Live writeback into source systems | Not supported |
| Hosted service / multi-user cloud app | Not supported |

## What Praxis Does Not Do Yet

Praxis is early-stage and intentionally local-first.

It is not a hosted service, not a production vector database, and not a full autonomous agent runtime. It does not automatically promote provisional graph updates into high-trust skills or policies, and it does not ship with private corpora or user-specific connectors.

Praxis Reach is also not a live CRM, ads-platform, analytics replacement, or warehouse. The current Reach module ships with mock and fixture connectors, plus experimental HubSpot, Google Ads, and Google Analytics connector classes. Real connectors should be read-only first, source-linked, permission-scoped, and designed so systems of record stay where they are.
