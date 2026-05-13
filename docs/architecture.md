# Praxis Architecture

Praxis separates durable knowledge from runtime-specific agent behavior.

```mermaid
flowchart TD
    A["Praxis Core"] --> B["Archive"]
    A --> C["Index"]
    A --> D["Graph"]
    A --> E["Bench"]
    A --> F["Forge"]

    B --> G["Source captures"]
    C --> H["Vector / hybrid retrieval"]
    D --> I["Concept, source, failure, practice relationships"]
    D --> R["Audited change sets and rollback"]
    E --> J["Retrieval evals and health checks"]
    F --> K["Agent Skills and workflow exports"]

    K --> L["Codex adapter"]
    K --> M["Claude Code adapter"]
    H --> N["LangGraph adapter"]
    H --> O["LlamaIndex adapter"]
    H --> P["Haystack adapter"]
    D --> Q["Mem0 / memory adapter"]
```

## Design Principle

The core should be stable and boring. Adapters can change quickly.

Praxis Core owns:

- source identity and provenance
- source captures and summaries
- chunk metadata and embedding records
- graph nodes, edges, evidence, confidence state, and audit logs
- watchlists and refresh state
- skill proposals and generated references
- eval results and health checks

Adapters own:

- where skills are installed
- how retrieval is exposed to a runtime
- how memory is imported/exported
- how a framework invokes Praxis tools
- how provider-specific embeddings or vector stores are configured

## Canonical Flow

```mermaid
sequenceDiagram
    participant User
    participant Scribe as Praxis Scribe
    participant Archive as Praxis Archive
    participant Graph as Praxis Graph
    participant Index as Praxis Index
    participant Forge as Praxis Forge
    participant Agent

    User->>Scribe: capture source
    Scribe->>Archive: save raw, summary, metadata
    Scribe->>Graph: auto-apply provisional graph update
    Graph->>Graph: append audited change set
    Archive->>Index: chunk and embed
    User->>Graph: inspect, promote, deprecate, or rollback
    Graph->>Forge: identify skill/workflow implications
    Forge->>Agent: export runtime-specific skill
    Agent->>Index: retrieve context during work
    Agent->>Graph: inspect relationships during work
```

## Near-Term Adapter Order

1. Codex adapter: provide one concrete agent-runtime export path.
2. Agent Skills exporter: write runtime-neutral `SKILL.md` packages.
3. Claude Code adapter: install/export compatible skills.
4. MCP server: expose Praxis to any MCP-compatible agent.
5. Framework adapters: LangGraph, LlamaIndex, Haystack.
6. Memory adapter: Mem0 import/export.
