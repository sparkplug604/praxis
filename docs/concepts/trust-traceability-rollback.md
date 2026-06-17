# Trust, Traceability, And Rollback

Praxis treats memory as evidence, not truth.

The goal is to let agents move quickly without turning source knowledge, live evidence, or client context into an untraceable junk drawer.

## Source Knowledge

For source knowledge, captured material is stored with source context so claims can be checked later.

SkillGraph updates are provisional by default. Every graph mutation is logged as a change set with before/after records, and reverted, merged, or deprecated graph objects are hidden from normal search/export unless you explicitly inspect them.

Useful commands:

```bash
praxis changes list
praxis rollback <change_set_id>
praxis conflicts list
praxis dedupe list
```

## Live Organizational Data

For live organizational data, Reach is read-only by design at this stage.

It stores evidence cards, query metadata, source links, timestamps, freshness checks, aggregate summaries, and warnings. It does not store secrets, does not write back to source systems, and does not try to become a CRM, ads platform, analytics tool, or warehouse.

## Client Data

For client data, Reach for Agencies keeps each client in a separate capsule with its own systems, field maps, metrics, permissions, evidence, context packs, and lifecycle state.

Client offboarding is staged through archive, export, delete-plan, delete, quarantine, and purge commands. Local Praxis deletion affects local Praxis artifacts only; it does not delete records inside client systems.

## Conflict Ledger

Praxis keeps a Conflict Ledger.

Ingest and promotion can log duplicate sources, duplicate content, possible duplicate entities, and likely claim contradictions. Reach can attach GTM-specific conflict warnings when operational sources disagree.

Search can show conflict warnings with `--explain`, exports can refuse unresolved conflicts with `--fail-on-open-conflicts`, and dedupe merges are reversible through audited change sets.

## Current Boundary

Praxis does not automatically promote every provisional graph update into trusted policy or agent behavior. Review, status, source authority, and rollback remain explicit parts of the workflow.

## Read Next

- [Praxis Core Governance](../modules/core/governance.md)
- [Praxis Authority Anchors](../modules/core/authority.md)
- [Conflicts And Dedupe](../modules/core/conflicts-and-dedupe.md)
