# Praxis Adapters

Adapters keep Praxis agent-agnostic.

The core database, graph, captures, and retrieval tools should not depend on Codex, Claude Code, LangGraph, LlamaIndex, Haystack, or Mem0. Each adapter translates Praxis artifacts into the expectations of a specific runtime.

## Adapter Contract

An adapter should declare:

- target runtime or framework
- artifacts it reads from Praxis
- artifacts it writes or installs
- commands it exposes
- verification or rollback procedure
- trust/safety boundaries

## Planned Adapters

- `agents/codex`: install Praxis skills into `~/.codex/skills`.
- `agents/claude-code`: export/install Agent Skills for Claude Code.
- `frameworks/langgraph`: expose Praxis retrieval/graph as LangGraph tools or nodes.
- `frameworks/llamaindex`: expose Praxis as a reader, retriever, or tool.
- `frameworks/haystack`: expose Praxis as components for pipelines.
- `memory/mem0`: import/export selected memories and evidence.

