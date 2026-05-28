# Praxis CLI

Praxis exposes one package command:

```bash
praxis --help
praxis <command> --help
```

If the `praxis` command is not on PATH, use Python's module form:

```bash
python3 -m praxis --help
python3 -m praxis <command> --help
```

On Windows PowerShell:

```powershell
py -m praxis --help
py -m praxis <command> --help
```

Praxis is currently checkout/workspace-oriented. The CLI expects a Praxis root containing `scripts/`, `db/`, `kg/`, `research/`, and `vectors/`.

If you run the CLI outside the checkout, pass `--root /path/to/Praxis` or set `PRAXIS_ROOT`.

Important: `ingest`, `search`, `graph`, and other actions are Praxis subcommands. Run `praxis ingest "https://example.com/source"` or `py -m praxis ingest "https://example.com/source"`, not `ingest "https://example.com/source"` by itself.

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
praxis search "knowledge to skill loop" --explain
praxis graph search "SkillGraph"
```

Capture a source and auto-apply provisional graph memory:

```bash
praxis ingest "https://example.com/source"
```

Windows/PATH-safe form:

```powershell
py -m praxis ingest "https://example.com/source"
```

Inspect or rollback graph changes:

```bash
praxis changes list
praxis changes show "chg:..."
praxis promote "chg:..."
praxis deprecate "chg:..."
praxis rollback "chg:..."
praxis rollback "chg:..." --force
```

Inspect and resolve conflict/dedupe records:

```bash
praxis conflicts list
praxis conflicts show "conflict:..."
praxis conflicts resolve "conflict:..." --resolution "keep_both_with_scope" --notes "Different scopes."
praxis dedupe list
praxis dedupe show "conflict:duplicate_entity:..."
praxis dedupe merge "conflict:duplicate_entity:..." --canonical "node:id"
praxis dedupe split "chg:..."
```

Refresh retrieval indexes:

```bash
praxis chunk --changed-only
praxis embed --provider local-hash
```

Export with conflict safety:

```bash
praxis export-graph --include-conflict-notes
praxis export-graph --fail-on-open-conflicts
praxis export-skill-refs --fail-on-open-conflicts
praxis export-skill-refs --include-conflict-notes
```

## Script Wrappers

The `scripts/` folder contains compatibility wrappers around the packaged CLI. They are useful when running from a checkout without installing the package.

```bash
python3 scripts/hybrid_search.py "test-backed refactoring"
python3 scripts/search_skill_graph.py search "refactoring"
python3 scripts/ingest_source.py "https://example.com/source"
python3 scripts/conflicts.py list
python3 scripts/dedupe.py list
python3 scripts/graph_changes.py list
python3 scripts/promote_graph_change.py "chg:..."
python3 scripts/deprecate_graph_change.py "chg:..."
python3 scripts/rollback_graph_change.py "chg:..."
python3 scripts/research_source.py "https://example.com/source"
python3 scripts/propose_graph_update.py "cap:source-id:hash"
python3 scripts/apply_graph_update.py "research/proposals/proposal.json" --dry-run
python3 scripts/chunk_sources.py --changed-only
python3 scripts/index_vectors.py --provider local-hash
python3 scripts/eval_retrieval.py
python3 scripts/skill_doctor.py
```
