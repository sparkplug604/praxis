# Praxis Adapters

Adapters are optional bridges from Praxis into agent runtimes and AI frameworks.

You do not need this folder to install Praxis, run the Core demo, run Reach
fixtures, or evaluate the Agency workflow. Start with the main
[README](../README.md), [Getting Started](../docs/getting-started.md), or the
[docs index](../docs/README.md) if you are trying Praxis for the first time.

For the fastest first run:

```bash
praxis demo core
```

The purpose of this folder is to keep Praxis agent-agnostic. The core database,
graph, captures, evidence cards, and retrieval tools should not depend on Codex,
Claude Code, LangGraph, LlamaIndex, Haystack, Mem0, or any other runtime. An
adapter translates Praxis artifacts into the expectations of one target runtime.

## What Belongs Here

Use `adapters/` for runtime and framework integration notes, prototypes, and
contracts.

Examples:

- installing exported Praxis skills into an agent runtime;
- exposing Praxis retrieval as framework tools or nodes;
- importing or exporting selected memories for another memory system;
- documenting verification and rollback behavior for a runtime bridge.

## What Does Not Belong Here

Reach data connectors do not live here. CRM, ads, analytics, and warehouse
connectors are part of Praxis Reach and are documented under
[docs/connectors](../docs/README.md#connectors).

Core intake parser helpers also do not live here. Optional media, OCR, document,
speech, or visual embedding helpers belong to the Core intake layer because they
convert sources before capture.

If an integration talks to an external business data source, it is probably a
Reach connector. If it translates Praxis knowledge into an agent/runtime format,
it probably belongs here.

## Current Status

This folder is a design surface, not a required runtime package. The planned
adapter contracts below describe the intended boundaries before the adapters are
implemented and hardened.

## Adapter Contract

An adapter should declare:

- target runtime or framework;
- artifacts it reads from Praxis;
- artifacts it writes or installs;
- commands it exposes;
- verification or rollback procedure;
- trust/safety boundaries.

## Planned Adapters

- `agents/codex`: install Praxis skills into `~/.codex/skills`.
- `agents/claude-code`: export/install Agent Skills for Claude Code.
- `frameworks/langgraph`: expose Praxis retrieval/graph as LangGraph tools or nodes.
- `frameworks/llamaindex`: expose Praxis as a reader, retriever, or tool.
- `frameworks/haystack`: expose Praxis as components for pipelines.
- `memory/mem0`: import/export selected memories and evidence.

## Maintainer Notes

Keep adapters thin. They should call stable Praxis commands, exported artifacts,
or package APIs instead of duplicating Core, Reach, or Agency logic.

Each adapter should include a small verification path before it is presented as
usable. A good minimum is:

1. generate or read a fixture Praxis artifact;
2. install or expose it through the target runtime;
3. run one smoke command;
4. document how to undo or remove what was installed.
