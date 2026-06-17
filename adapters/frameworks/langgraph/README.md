# LangGraph Adapter

The LangGraph adapter should expose Praxis as tools or graph nodes for stateful agents.

Praxis should not replace LangGraph. LangGraph owns state, orchestration,
durable execution, and human-in-the-loop workflow control. Praxis should supply
governed context: source-linked retrieval results, graph hints, freshness,
trust, conflicts, and rollback-aware memory metadata.

For the broader comparison with LangChain, LangSmith, and Langflow, read
[Praxis With LangChain, LangSmith, And Langflow](../../../docs/integrations/langchain-langsmith-langflow.md).

## Potential Tools

- `praxis_search(query)`
- `praxis_graph_neighbors(node_id)`
- `praxis_capture_source(uri)`
- `praxis_propose_graph_update(capture_id)`
- `praxis_run_eval(target)`

## Proposed Graph Shape

```text
user query
-> classify need for context
-> praxis_search node
-> inspect warnings
-> generate answer, ask for review, or continue workflow
```

## Adapter Boundary

A future adapter should:

- call a stable Praxis package API, not duplicate Core search logic;
- return structured result artifacts with `source_id`, `capture_id`, priority,
  freshness, trust, and conflict metadata;
- expose retrieval as one graph node or tool, not as a full agent runtime;
- include a fixture smoke test before the adapter is described as usable.
