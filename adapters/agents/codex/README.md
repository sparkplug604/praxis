# Codex Adapter

The Codex adapter exports Praxis skill packages into a Codex-compatible skills directory.

## Current Shape

- Praxis search is available through local CLI scripts.
- Codex-compatible skills can point at Praxis as their shared memory/retrieval layer.
- Install paths should be configurable; `~/.codex/skills` is only a conventional default.

## Target Shape

- Generate/install a `praxis-memory` skill into a configured Codex skills directory.
- Keep durable writes source-linked, confidence-tagged, audited, and rollback-capable.
- Expose common commands: hybrid search, graph search, ingest, source capture, change inspection, rollback, indexing, doctor.
- Support rollback by preserving prior skill directories before overwriting.
