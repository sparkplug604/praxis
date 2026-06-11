"""Client artifact discovery and safe local cleanup for Praxis Agency."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from praxis.paths import kg_dir, research_dir, vectors_dir
from praxis.reach.storage import (
    client_dir,
    context_dir,
    evidence_dir,
    fixtures_dir,
    reach_dir,
    read_json,
    reach_conflicts_dir,
    slug,
)


@dataclass(frozen=True)
class LifecycleTarget:
    kind: str
    path: Path
    reason: str

    def to_dict(self, root: Path) -> dict[str, str]:
        return {
            "kind": self.kind,
            "path": rel(root, self.path),
            "reason": self.reason,
        }


def collect_client_targets(root: Path, client_id: str) -> list[LifecycleTarget]:
    client_id = slug(client_id)
    targets: list[LifecycleTarget] = []
    capsule_dir = client_dir(root, client_id)
    if capsule_dir.exists():
        targets.append(LifecycleTarget(kind="dir", path=capsule_dir, reason="client capsule configuration"))
    context_path = context_dir(root) / client_id
    if context_path.exists():
        targets.append(LifecycleTarget(kind="dir", path=context_path, reason="generated context packs"))
    fixture_path = fixtures_dir(root) / client_id
    if fixture_path.exists():
        targets.append(LifecycleTarget(kind="dir", path=fixture_path, reason="client fixture data"))
    targets.extend(_client_evidence_targets(root, client_id))
    targets.extend(_client_conflict_targets(root, client_id))
    targets.extend(_client_evidence_source_targets(root, client_id))
    targets.extend(_client_research_capture_targets(root, client_id))
    return _dedupe_targets(targets)


def collect_database_records(root: Path, client_id: str) -> dict[str, Any]:
    source_ids = _reach_source_ids(root, client_id)
    if not source_ids:
        return {"source_ids": [], "kg": {}, "vectors": {}}
    return {
        "source_ids": source_ids,
        "kg": _count_kg_records(root, source_ids),
        "vectors": _count_vector_records(root, source_ids),
    }


def purge_database_records(root: Path, client_id: str) -> dict[str, Any]:
    source_ids = _reach_source_ids(root, client_id)
    return {
        "kg": _delete_kg_records(root, source_ids),
        "vectors": _delete_vector_records(root, source_ids),
    }


def assert_safe_target(root: Path, client_id: str, path: Path, kind: str) -> None:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not is_relative_to(resolved, resolved_root):
        raise RuntimeError(f"Refusing to delete outside Praxis root: {path}")
    if kind not in {"file", "dir"}:
        raise RuntimeError(f"Unsupported target kind: {kind}")

    allowed_dirs = [
        client_dir(root, client_id).resolve(),
        (context_dir(root) / client_id).resolve(),
        (fixtures_dir(root) / client_id).resolve(),
    ]
    if any(resolved == allowed or is_relative_to(resolved, allowed) for allowed in allowed_dirs):
        return

    if is_relative_to(resolved, evidence_dir(root).resolve()) and path.suffix == ".json":
        data = read_json(path)
        if data.get("client_id") == client_id:
            return
    if is_relative_to(resolved, reach_conflicts_dir(root).resolve()) and path.suffix == ".json":
        data = read_json(path)
        if data.get("client_id") == client_id:
            return
    evidence_sources = (reach_dir(root) / "evidence_sources").resolve()
    if is_relative_to(resolved, evidence_sources) and path.suffix == ".md":
        text = path.read_text(encoding="utf-8", errors="replace")
        if f"client_id: `{client_id}`" in text:
            return
    captures = (research_dir(root) / "captures").resolve()
    if is_relative_to(resolved, captures):
        for metadata_path in path.glob("*.metadata.json") if path.is_dir() else []:
            data = read_json(metadata_path)
            if data.get("source_type") == "reach_evidence" and _source_id_belongs_to_client(str(data.get("source_id") or ""), client_id):
                return
    raise RuntimeError(f"Refusing unsafe delete target for {client_id}: {rel(root, path)}")


def rel(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _client_evidence_targets(root: Path, client_id: str) -> list[LifecycleTarget]:
    targets: list[LifecycleTarget] = []
    for path in sorted(evidence_dir(root).glob("*.json")) if evidence_dir(root).exists() else []:
        try:
            data = read_json(path)
        except json.JSONDecodeError:
            continue
        if data.get("client_id") == client_id:
            targets.append(LifecycleTarget(kind="file", path=path, reason="Reach evidence card"))
    return targets


def _client_conflict_targets(root: Path, client_id: str) -> list[LifecycleTarget]:
    targets: list[LifecycleTarget] = []
    for path in sorted(reach_conflicts_dir(root).glob("*.json")) if reach_conflicts_dir(root).exists() else []:
        try:
            data = read_json(path)
        except json.JSONDecodeError:
            continue
        if data.get("client_id") == client_id:
            targets.append(LifecycleTarget(kind="file", path=path, reason="Reach conflict record"))
    return targets


def _client_evidence_source_targets(root: Path, client_id: str) -> list[LifecycleTarget]:
    base = reach_dir(root) / "evidence_sources"
    targets: list[LifecycleTarget] = []
    if not base.exists():
        return targets
    needle = f"client_id: `{client_id}`"
    for path in sorted(base.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle in text:
            targets.append(LifecycleTarget(kind="file", path=path, reason="Core source file generated from Reach evidence"))
    return targets


def _client_research_capture_targets(root: Path, client_id: str) -> list[LifecycleTarget]:
    targets: list[LifecycleTarget] = []
    base = research_dir(root) / "captures"
    if not base.exists():
        return targets
    for metadata_path in sorted(base.glob("*/**/*.metadata.json")):
        try:
            data = read_json(metadata_path)
        except json.JSONDecodeError:
            continue
        source_id = str(data.get("source_id") or "")
        source_type = str(data.get("source_type") or "")
        if source_type == "reach_evidence" and _source_id_belongs_to_client(source_id, client_id):
            targets.append(LifecycleTarget(kind="dir", path=metadata_path.parent, reason="Praxis Core capture generated from Reach evidence"))
    return targets


def _reach_source_ids(root: Path, client_id: str) -> list[str]:
    db = kg_dir(root) / "skill_graph.sqlite"
    if not db.exists() or not _table_exists(db, "source_registry"):
        return []
    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            """
            SELECT id
            FROM source_registry
            WHERE source_type = 'reach_evidence'
            """
        ).fetchall()
    return sorted(str(row[0]) for row in rows if _source_id_belongs_to_client(str(row[0]), client_id))


def _source_id_belongs_to_client(source_id: str, client_id: str) -> bool:
    # Reach evidence source ids look like:
    # src:reach-evidence:<query_id>:<client_id>:<query_hash>
    parts = source_id.split(":")
    return len(parts) >= 5 and parts[0] == "src" and parts[1] == "reach-evidence" and parts[3] == client_id


def _count_kg_records(root: Path, source_ids: list[str]) -> dict[str, int]:
    db = kg_dir(root) / "skill_graph.sqlite"
    if not source_ids or not db.exists():
        return {}
    counts: dict[str, int] = {}
    with sqlite3.connect(db) as connection:
        for table, column in [("source_registry", "id"), ("source_captures", "source_id"), ("graph_update_proposals", "source_id")]:
            if _table_exists(db, table):
                counts[table] = _count_rows(connection, table, column, source_ids)
    return counts


def _count_vector_records(root: Path, source_ids: list[str]) -> dict[str, int]:
    db = vectors_dir(root) / "semantic_index.sqlite"
    if not source_ids or not db.exists():
        return {}
    counts: dict[str, int] = {}
    with sqlite3.connect(db) as connection:
        for table, column in [("semantic_documents", "source_id"), ("semantic_chunks", "source_id")]:
            if _table_exists(db, table):
                counts[table] = _count_rows(connection, table, column, source_ids)
    return counts


def _delete_kg_records(root: Path, source_ids: list[str]) -> dict[str, int]:
    db = kg_dir(root) / "skill_graph.sqlite"
    if not source_ids or not db.exists():
        return {}
    counts = _count_kg_records(root, source_ids)
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        if _table_exists(db, "source_registry"):
            connection.executemany("DELETE FROM source_registry WHERE id = ?", [(source_id,) for source_id in source_ids])
    return counts


def _delete_vector_records(root: Path, source_ids: list[str]) -> dict[str, int]:
    db = vectors_dir(root) / "semantic_index.sqlite"
    if not source_ids or not db.exists():
        return {}
    counts = _count_vector_records(root, source_ids)
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        chunk_ids: list[str] = []
        if _table_exists(db, "semantic_chunks"):
            chunk_ids = [
                str(row[0])
                for row in connection.execute(
                    f"SELECT id FROM semantic_chunks WHERE source_id IN ({_placeholders(source_ids)})",
                    source_ids,
                ).fetchall()
            ]
        if chunk_ids:
            if _table_exists(db, "semantic_chunks_fts"):
                connection.executemany("DELETE FROM semantic_chunks_fts WHERE chunk_id = ?", [(chunk_id,) for chunk_id in chunk_ids])
            if _table_exists(db, "chunk_embeddings"):
                connection.executemany("DELETE FROM chunk_embeddings WHERE chunk_id = ?", [(chunk_id,) for chunk_id in chunk_ids])
        if _table_exists(db, "semantic_documents"):
            connection.execute(f"DELETE FROM semantic_documents WHERE source_id IN ({_placeholders(source_ids)})", source_ids)
        if _table_exists(db, "semantic_chunks"):
            connection.execute(f"DELETE FROM semantic_chunks WHERE source_id IN ({_placeholders(source_ids)})", source_ids)
    return counts


def _count_rows(connection: sqlite3.Connection, table: str, column: str, values: list[str]) -> int:
    row = connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {column} IN ({_placeholders(values)})",
        values,
    ).fetchone()
    return int(row[0]) if row else 0


def _table_exists(db: Path, table: str) -> bool:
    with sqlite3.connect(db) as connection:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
            (table,),
        ).fetchone()
    return row is not None


def _dedupe_targets(targets: list[LifecycleTarget]) -> list[LifecycleTarget]:
    seen: set[Path] = set()
    out: list[LifecycleTarget] = []
    for item in targets:
        key = item.path.resolve()
        if key in seen:
            continue
        out.append(item)
        seen.add(key)
    return out


def _placeholders(values: list[str]) -> str:
    return ",".join("?" for _ in values)
