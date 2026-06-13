# Maintenance And Hygiene

Praxis Core includes local maintenance tools so the knowledge layer can change without becoming opaque.

Run the basic health check:

```bash
praxis doctor --require-index
```

## Hygiene Goals

Core hygiene is about keeping local knowledge:

- source-linked;
- searchable;
- reversible;
- deduplicated where possible;
- honest about uncertainty;
- explicit about conflicts;
- safe to reuse in skill exports and agent workflows.

## Health Checks

Use doctor commands to verify local state:

```bash
praxis doctor --require-index
praxis authority verify --strict
praxis governance doctor --init
```

These checks help catch missing databases, missing authority state, broken governance ledgers, and other local setup issues.

## Change Sets

Graph updates are recorded as change sets.

Inspect them with:

```bash
praxis changes list
praxis changes show "chg:..."
```

Change sets make graph mutations reviewable. A bad update can be rolled back instead of manually deleted.

```bash
praxis rollback "chg:..."
```

## Status Management

Core uses status fields so old or risky knowledge can be hidden from normal use without deleting history.

Relevant statuses include:

- `provisional`;
- `active`;
- `deprecated`;
- `reverted`;
- `merged`;
- `suppressed`;
- `needs_review`.

This is one of the main differences between Praxis and a basic chunk store. Knowledge can be downgraded, merged, or rolled back with records attached.

## Conflict Review

Core can log conflicts during ingest, graph updates, dedupe review, and Reach evidence generation.

Inspect conflicts with:

```bash
praxis conflicts list
praxis conflicts show "conflict:..."
```

Resolve or acknowledge a conflict with:

```bash
praxis conflicts resolve "conflict:..." --resolution "accepted current source" --status resolved
```

See [Conflicts And Dedupe](conflicts-and-dedupe.md).

## Dedupe Review

Core separates dedupe review from automatic deletion.

```bash
praxis dedupe list
praxis dedupe show "conflict:..."
praxis dedupe merge "conflict:..." --canonical "node:..."
```

Dedupe merges create change sets, and merges can be split again:

```bash
praxis dedupe split "chg:..."
```

## Authority And Governance

Authority anchors define which source is allowed to settle a type of claim.

```bash
praxis authority init
praxis authority compile
praxis authority verify --strict
```

Governance checks evaluate whether evidence can be reused safely.

```bash
praxis governance evaluate \
  --claim-type entity_identity \
  --source entity_annotation \
  --evidence "ann:..."
```

See [Praxis Authority Anchors](authority.md) and [Praxis Core Governance](governance.md).

## Workspace Migration

Praxis prefers generated state under `workspace/`.

Older checkouts may still have runtime folders at the repo root. Review and apply migration with:

```bash
praxis migrate-workspace --plan
praxis migrate-workspace --apply
```

## Current Boundary

Core hygiene is local and inspectable. It is not a hosted enterprise policy engine. The current tools help you review, warn, rollback, and gate reuse; they do not remove the need for human review on ambiguous or high-risk knowledge.
