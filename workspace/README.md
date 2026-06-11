# Praxis Workspace

`workspace/` is the local runtime area for generated Praxis state.

Praxis writes databases, source captures, vector indexes, evidence cards,
context packs, client capsules, generated skills, exports, and notes here.

Most files under this folder are ignored by git so private or generated data is
not committed by accident. The `.gitkeep` files only preserve the folder shape
for a fresh checkout.

If you have an older checkout with runtime data in root-level folders such as
`db/`, `kg/`, `vectors/`, `research/`, `reach/`, or `agency/`, run:

```bash
praxis migrate-workspace --plan
praxis migrate-workspace --apply
```
