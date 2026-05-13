# Praxis CLI

Praxis exposes one package command:

```bash
praxis --help
praxis <command> --help
```

Praxis is currently checkout/workspace-oriented. The CLI expects a Praxis root containing `scripts/`, `db/`, `kg/`, `research/`, and `vectors/`.

If you run the CLI outside the checkout, pass `--root /path/to/Praxis` or set `PRAXIS_ROOT`.

## Common Commands

Initialize and check a checkout:

```bash
praxis bootstrap
praxis doctor --require-index
praxis eval
```

Search the corpus and SkillGraph:

```bash
praxis search "knowledge to skill loop"
praxis graph search "SkillGraph"
```

Capture a source and auto-apply provisional graph memory:

```bash
praxis ingest "https://example.com/source"
```

Inspect or rollback graph changes:

```bash
praxis changes list
praxis changes show "chg:..."
praxis rollback "chg:..."
```

Refresh retrieval indexes:

```bash
praxis chunk --changed-only
praxis embed --provider local-hash
```

## Script Wrappers

The `scripts/` folder contains compatibility wrappers around the packaged CLI. They are useful when running from a checkout without installing the package.

```bash
python3 scripts/hybrid_search.py "test-backed refactoring"
python3 scripts/search_skill_graph.py search "refactoring"
python3 scripts/ingest_source.py "https://example.com/source"
python3 scripts/graph_changes.py list
python3 scripts/rollback_graph_change.py "chg:..."
python3 scripts/research_source.py "https://example.com/source"
python3 scripts/propose_graph_update.py "cap:source-id:hash"
python3 scripts/apply_graph_update.py "research/proposals/proposal.json" --dry-run
python3 scripts/chunk_sources.py --changed-only
python3 scripts/index_vectors.py --provider local-hash
python3 scripts/eval_retrieval.py
python3 scripts/skill_doctor.py
```
