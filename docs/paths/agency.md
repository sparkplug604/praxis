# Agency Path

Use this path when you want to evaluate multi-client GTM workflows with client-specific systems, field maps, metrics, permissions, evidence, and context packs.

## Start Here

Run the Agency demo:

```bash
praxis demo agency
```

If `praxis` is not on your PATH:

```bash
python3 -m praxis demo agency
```

## What To Read Next

1. [Praxis Reach for Agencies](../modules/agency/README.md): how client capsules and multi-client runs work.
2. [Agency GTM Evaluation Guide](../modules/agency/evaluation.md): the fastest path for evaluating the agency model.
3. [Agency fixture demo](../tutorials/agency-fixture-demo.md): inspect two fixture-backed clients.
4. [Praxis Reach](../modules/reach/README.md): understand the evidence card and context pack layer underneath Agency.

## What Success Looks Like

Agency runs should show each client separately:

```text
client_id: acme
status: ok
context_pack: /path/to/workspace/reach/context_packs/...
```

## Current Boundary

The Agency fixture demo works locally and does not call live CRM, ads, analytics, or warehouse systems.

Live connector hardening, hosted multi-user permissions, writeback, row-level warehousing, and full compliance automation are separate product layers.
