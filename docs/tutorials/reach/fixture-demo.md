# Tutorial: Reach Fixture Demo

Praxis Reach shows how an agent can use operational evidence without copying a whole CRM or ads database into Praxis.

This demo uses fixture data, so no credentials are required.

## 1. Run The Setup Wizard

```bash
praxis setup --non-interactive --path reach-demo
```

Expected success output:

```text
Reach demo is ready.

You now have:
  - a fixture client capsule: demo
  - local fixture CRM/ad data
  - one Reach evidence card
  - one generated context pack
```

## 2. List Evidence

```bash
praxis reach evidence list --client demo
```

Expected output:

```text
ev:demo:weekly_gtm_review:...  demo  weekly_gtm_review  fresh
```

## 3. Inspect The Evidence Card

```bash
praxis reach evidence show "ev:..."
```

An evidence card includes:

- the query that was run;
- aggregate metrics;
- freshness metadata;
- source links;
- warnings and conflict records;
- whether the data is complete or partial.

## 4. Build A Context Pack

```bash
praxis reach context build weekly_gtm_review --client demo
```

Expected output:

```text
context_pack: /path/to/reach/context_packs/demo/weekly_gtm_review-....md
```

The context pack is the agent-facing summary. It gives the agent enough GTM context to work without dumping a whole live data system into the prompt.

## 5. Try The Same Flow Manually

```bash
praxis reach init
praxis agency fixture create demo --profile b2b-saas --overwrite
praxis agency run weekly_gtm_review --clients demo --context
praxis reach stale list --client demo
```

Use this once the wizard flow makes sense and you want to see each step.
