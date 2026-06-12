# Praxis Core Governance

Praxis Core Governance is the control layer around source-backed memory.

It does not decide that a claim is universally true. It checks whether evidence is present, usable, fresh enough, conflict-aware, and allowed by the configured source-of-record rules.

## What This Solves

RAG and memory systems can retrieve useful text while still leaving important questions unanswered:

- Does this result have a source?
- Is the evidence still active?
- Is there an unresolved conflict attached to it?
- Which system is allowed to settle this claim?
- Did Praxis record why a piece of evidence was allowed, warned, or blocked?

Core Governance turns those checks into inspectable CLI behavior and a local event ledger.

## What It Does Today

The first implementation supports:

- `praxis governance init` for local governance storage;
- `praxis governance doctor` for governance, authority, and conflict health checks;
- `praxis governance evaluate` for deterministic evidence reuse checks;
- `praxis governance events` for policy evaluation records;
- `praxis governance ledger verify` for hash-chain receipt verification;
- governance warnings in `praxis search --explain`;
- strict governance gates for `praxis export-graph` and `praxis export-skill-refs`.

## Basic Flow

```bash
praxis governance init
praxis governance doctor --init
praxis governance evaluate \
  --claim-type pipeline_metric \
  --client acme \
  --source hubspot \
  --evidence "ev:pipeline:acme:1"
praxis governance events list
praxis governance ledger verify
```

## Relationship To Authority Anchors

Authority Anchors define the source-of-record rules.

Core Governance uses those rules as one input during policy evaluation. It also checks the evidence object itself and writes a governance event so the decision is auditable later.

In plain terms:

- `praxis authority` manages source authority rules and adjudication records.
- `praxis governance` checks evidence reuse, conflict state, authority decisions, and governance ledger health.

## Export Safety

Skill and graph exports can be run with stricter checks:

```bash
praxis export-skill-refs --strict-governance
praxis export-graph --strict-governance
praxis export-skill-refs --strict-governance --governance-threshold error
praxis export-graph --strict-governance --governance-threshold error
```

By default, strict exports refuse export when governance health checks contain warnings or errors. Use `--governance-threshold error` when warnings should stay visible but only errors should block export.

## Current Limits

This is a local, early governance layer.

It does not yet provide signed receipts, multi-user permissions, remote attestation, policy approvals, or enterprise-grade tamper resistance. The current ledger is hash-chained for local auditability, not adversarial security.
