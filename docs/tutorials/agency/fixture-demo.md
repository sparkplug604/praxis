# Tutorial: Agency Fixture Demo

Praxis Reach for Agencies adds per-client capsules on top of Reach. Each capsule stores the client's systems, field maps, metric definitions, permissions, and fixture or connector settings.

This demo creates two fixture clients and runs one workflow across both.

## 1. Run The Setup Wizard

```bash
praxis setup --non-interactive --path agency-demo
```

Expected success output:

```text
Agency demo is ready.

You now have:
  - two fixture client capsules
  - per-client evidence cards
  - per-client context packs
  - a stale/fresh context report
```

## 2. List Clients

```bash
praxis agency client list
```

Expected output:

```text
acme: Acme ...
beta: Beta ...
```

## 3. Run A Workflow Across Clients

```bash
praxis agency run weekly_gtm_review --clients acme,beta --context
```

Expected output:

```text
client_id: acme
status: ok
context_pack: ...

client_id: beta
status: ok
context_pack: ...
```

## 4. Check Freshness

```bash
praxis agency stale-context-report --all
```

Expected output:

```text
acme: fresh
beta: fresh
```

## 5. Why This Matters

Agencies usually have clients with different CRMs, ad platforms, field names, permissions, and reporting habits. The client capsule gives Praxis a stable contract for each client without forcing every client into the same database shape.

The goal is not to clone every client's operational data. The goal is to keep source systems as the source of truth, then create evidence cards and context packs that agents can safely use.
