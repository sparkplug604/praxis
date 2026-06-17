# Conflicts And Dedupe

Praxis Core uses a conflict ledger to keep suspicious knowledge visible instead of silently overwriting it.

List open conflicts:

```bash
praxis conflicts list
```

## What A Conflict Means

A conflict is not a final truth judgment.

It is a review record that says: "These objects may duplicate, contradict, or weaken each other. Inspect before reusing them as durable knowledge."

## Conflict Sources

Core can record conflicts for:

- duplicate URLs;
- duplicate source IDs;
- duplicate content hashes;
- similar source titles;
- possible duplicate entities;
- claim-like contradictions;
- operational evidence disagreement from Reach.

Relationship Evidence also has a narrower review queue for relationship-promotion issues, such as one-to-one cardinality conflicts. Those review items are managed with:

```bash
praxis relationship-evidence review list
praxis relationship-evidence review show "relationship-review:..."
```

Use the conflict ledger for broad source, graph, entity, and evidence conflicts. Use Relationship Evidence review items for extracted relationship candidates that need inspection before promotion.

## Inspecting Conflicts

Use:

```bash
praxis conflicts list
praxis conflicts show "conflict:..."
```

A conflict record can include:

- conflict type;
- severity;
- status;
- summary;
- linked source, capture, node, or evidence objects;
- rationale metadata;
- resolver notes.

## Resolving Conflicts

Resolve, suppress, acknowledge, or mark a conflict as a false positive:

```bash
praxis conflicts resolve "conflict:..." \
  --resolution "kept newer source as canonical" \
  --notes "older source is retained for history" \
  --status resolved
```

Status matters because open and acknowledged conflicts can affect search priority.

## Dedupe Candidates

Dedupe is a focused workflow for duplicate-like conflicts.

```bash
praxis dedupe list
praxis dedupe show "conflict:..."
```

For duplicate entities, Core can merge duplicate nodes into a canonical node:

```bash
praxis dedupe merge "conflict:..." --canonical "account:acme"
```

The merge:

- creates a graph change set;
- preserves aliases from duplicate nodes;
- marks duplicate nodes as merged;
- records the merge on the conflict;
- prints an undo command.

Undo a dedupe merge:

```bash
praxis dedupe split "chg:..."
```

## How Conflicts Affect Retrieval

Hybrid search can include conflict warnings in explanation output:

```bash
praxis search "Acme pipeline" --entity-aware --explain
```

Context priority can apply conflict penalties for open or acknowledged conflicts. That means a result can still appear, but it may rank lower or carry warnings when unresolved conflicts are attached.

## How Conflicts Affect Export

Core can refuse exports when unresolved conflicts should block reuse.

For skill/reference export workflows, this keeps unresolved source or graph problems from quietly entering reusable agent instructions.

## Current Boundary

The conflict ledger helps review suspicious knowledge. It does not automatically decide truth. Human review, authority anchors, governance checks, and rollbackable change sets are still part of the workflow.
