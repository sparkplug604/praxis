# Tutorial: Core First Source

This tutorial gets Praxis Core from an empty checkout to a searchable source.

## 1. Install

```bash
python3 -m pip install -e .
```

Windows PowerShell:

```powershell
py -m pip install -e .
```

## 2. Initialize Praxis

```bash
praxis bootstrap
praxis doctor --require-index
```

Expected success output:

```text
Praxis doctor
ok: README.md: ...
ok: praxis.sqlite table sources: ...
ok: skill_graph.sqlite table nodes: ...
ok: semantic_index.sqlite table semantic_chunks: ...
status: ok
```

If `praxis` is not recognized, use `python3 -m praxis` or `py -m praxis` instead.

## 3. Ingest One Source

```bash
praxis ingest "https://example.com/source"
```

Expected success output:

```text
capture_id: cap:...
proposal: workspace/research/proposals/...
change_set: chg:...
status: applied
```

Praxis captures the source, preserves evidence, proposes SkillGraph memory, applies it as provisional knowledge, and logs the change set.

## 4. Search With Explanations

```bash
praxis search "what did this source teach us?" --explain
```

Expected success output:

```text
score: ...
priority: ...
source: cap:...
why: semantic match, keyword match, graph hints
```

Use `--rank-by relevance` if you want raw retrieval order instead of the default priority ranking.

## 5. Inspect Or Undo

```bash
praxis changes list
praxis changes show "chg:..."
praxis conflicts list
praxis rollback "chg:..."
```

Praxis keeps source evidence, audit logs, conflicts, and rollback commands attached so memory can move quickly without becoming a junk drawer.
