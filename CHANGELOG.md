# Changelog

## Unreleased

HTML capture now keeps labels and units with values in simple tables and infoboxes.
Unsupported layouts remain searchable as text and produce a warning. Existing captures
are unchanged; see [Checking HTML tables](docs/modules/core/intake.md#checking-html-tables)
to preview a source or refresh an older capture.

## 0.1.0 - 2026-05-15

Initial public release.

Praxis includes:

- source capture and ingestion for web links, local files, directories, notes, papers, and watchlist hits;
- local SQLite-backed archive, vector, relational, and SkillGraph stores;
- provisional SkillGraph memory with audited change sets;
- promote, deprecate, and rollback commands for reversible graph updates;
- local-hash embeddings and optional OpenAI embedding support;
- hybrid search across semantic chunks, keyword matches, and SkillGraph context;
- explainable retrieval output with source and graph hints;
- watchlist scanning for trusted research and web sources;
- export commands for graph and skill-reference artifacts;
- health checks and retrieval eval commands.
