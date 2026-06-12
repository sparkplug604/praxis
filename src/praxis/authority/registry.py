"""Storage and compilation for Praxis authority bundles."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from praxis.paths import authority_dir as workspace_authority_dir
from .models import AuthorityBundle, TruthAnchor, canonical_json, utc_now


DEFAULT_BUNDLE: dict[str, Any] = {
    "bundle_id": "bundle:default",
    "version": 1,
    "metadata": {
        "name": "Default Praxis authority anchors",
        "purpose": "Starter anchors for source-of-record adjudication. Edit before using in production.",
    },
    "anchors": [
        {
            "id": "anchor:default:operational_metric",
            "description": "Operational metrics should come from the configured system of record, not summaries.",
            "scope": {"claim_type": "operational_metric"},
            "authoritative_source": "system_of_record",
            "fallback_sources": ["evidence_card"],
            "forbidden_sources": ["llm_summary", "provisional_memory"],
            "freshness_sla_hours": 24,
            "conflict_behavior": "block_on_conflict",
            "required_evidence": ["evidence_id"],
            "safe_default": "ask_for_source_of_record",
        },
        {
            "id": "anchor:default:strategy_note",
            "description": "Strategy notes can inform context, but should not override operational records.",
            "scope": {"claim_type": "strategy_note"},
            "authoritative_source": "accepted_note",
            "fallback_sources": ["source_capture", "evidence_card"],
            "forbidden_sources": ["unattributed_memory"],
            "freshness_sla_hours": 2160,
            "conflict_behavior": "warn_and_report",
            "required_evidence": ["evidence_id"],
            "safe_default": "treat_as_context",
        },
    ],
    "invariants": [
        {
            "id": "invariant:authority:not_silent",
            "summary": "Authority bundles may be proposed by agents, but activation should be explicit and logged.",
            "severity": "high",
        },
        {
            "id": "invariant:authority:evidence_required",
            "summary": "Claims promoted to operational truth need source evidence or a configured exception.",
            "severity": "high",
        },
    ],
}


def authority_dir(root: Path) -> Path:
    return workspace_authority_dir(root)


def bundles_dir(root: Path) -> Path:
    return authority_dir(root) / "bundles"


def manifests_dir(root: Path) -> Path:
    return authority_dir(root) / "manifests"


def registry_path(root: Path) -> Path:
    return authority_dir(root) / "authority.sqlite"


def active_manifest_path(root: Path) -> Path:
    return manifests_dir(root) / "active.json"


def default_bundle_path(root: Path) -> Path:
    return bundles_dir(root) / "default.json"


def init_workspace(root: Path, *, force: bool = False) -> dict[str, str]:
    bundles_dir(root).mkdir(parents=True, exist_ok=True)
    manifests_dir(root).mkdir(parents=True, exist_ok=True)
    bundle_path = default_bundle_path(root)
    if force or not bundle_path.exists():
        bundle_path.write_text(json.dumps(DEFAULT_BUNDLE, indent=2) + "\n", encoding="utf-8")
    manifest_path = active_manifest_path(root)
    if force or not manifest_path.exists():
        manifest_path.write_text(
            json.dumps({"active_bundle": str(bundle_path.relative_to(root))}, indent=2) + "\n",
            encoding="utf-8",
        )
    return {"bundle_path": str(bundle_path), "manifest_path": str(manifest_path)}


def activate_bundle(root: Path, bundle_path: Path) -> dict[str, str]:
    """Point the active manifest at a bundle without compiling it."""

    manifests_dir(root).mkdir(parents=True, exist_ok=True)
    selected_path = bundle_path.expanduser().resolve()
    load_bundle(selected_path)
    try:
        manifest_value = str(selected_path.relative_to(root))
    except ValueError:
        manifest_value = str(selected_path)
    active_manifest_path(root).write_text(
        json.dumps({"active_bundle": manifest_value}, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"bundle_path": str(selected_path), "manifest_path": str(active_manifest_path(root))}


def load_bundle(path: Path) -> AuthorityBundle:
    payload = json.loads(path.read_text(encoding="utf-8"))
    bundle = AuthorityBundle.from_dict(payload)
    errors = bundle.validate()
    if errors:
        raise ValueError("Invalid authority bundle:\n" + "\n".join(f"- {error}" for error in errors))
    return bundle


def resolve_active_bundle_path(root: Path) -> Path:
    manifest_path = active_manifest_path(root)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Authority manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_path = Path(str(manifest.get("active_bundle") or ""))
    if not raw_path:
        raise ValueError(f"Authority manifest is missing active_bundle: {manifest_path}")
    if raw_path.is_absolute():
        return raw_path
    return (root / raw_path).resolve()


def connect(root: Path) -> sqlite3.Connection:
    authority_dir(root).mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(registry_path(root))
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS authority_bundles (
            bundle_id TEXT PRIMARY KEY,
            version INTEGER NOT NULL,
            bundle_hash TEXT NOT NULL,
            source_path TEXT NOT NULL,
            compiled_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS authority_anchors (
            anchor_id TEXT PRIMARY KEY,
            bundle_id TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            authoritative_source TEXT NOT NULL,
            fallback_sources_json TEXT NOT NULL,
            forbidden_sources_json TEXT NOT NULL,
            freshness_sla_hours INTEGER NOT NULL,
            conflict_behavior TEXT NOT NULL,
            required_evidence_json TEXT NOT NULL,
            safe_default TEXT NOT NULL,
            status TEXT NOT NULL,
            description TEXT NOT NULL,
            FOREIGN KEY(bundle_id) REFERENCES authority_bundles(bundle_id)
        );

        CREATE TABLE IF NOT EXISTS authority_invariants (
            invariant_id TEXT PRIMARY KEY,
            bundle_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY(bundle_id) REFERENCES authority_bundles(bundle_id)
        );

        CREATE TABLE IF NOT EXISTS adjudication_records (
            record_id TEXT PRIMARY KEY,
            request_hash TEXT NOT NULL,
            claim_type TEXT NOT NULL,
            source TEXT NOT NULL,
            client_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            reason TEXT NOT NULL,
            anchor_id TEXT NOT NULL,
            bundle_id TEXT NOT NULL,
            bundle_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            request_json TEXT NOT NULL,
            result_json TEXT NOT NULL
        );
        """
    )


def compile_bundle(root: Path, bundle_path: Path | None = None) -> dict[str, str]:
    init_workspace(root)
    selected_path = (bundle_path or resolve_active_bundle_path(root)).resolve()
    bundle = load_bundle(selected_path)
    bundle_hash = bundle.bundle_hash()
    compiled_at = utc_now().isoformat()

    with connect(root) as connection:
        connection.execute("DELETE FROM authority_invariants WHERE bundle_id = ?", (bundle.bundle_id,))
        connection.execute("DELETE FROM authority_anchors WHERE bundle_id = ?", (bundle.bundle_id,))
        connection.execute(
            """
            INSERT OR REPLACE INTO authority_bundles
            (bundle_id, version, bundle_hash, source_path, compiled_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                bundle.bundle_id,
                bundle.version,
                bundle_hash,
                str(selected_path),
                compiled_at,
                canonical_json(bundle.to_dict()),
            ),
        )
        for anchor in bundle.anchors:
            connection.execute(
                """
                INSERT OR REPLACE INTO authority_anchors
                (anchor_id, bundle_id, scope_json, authoritative_source, fallback_sources_json,
                 forbidden_sources_json, freshness_sla_hours, conflict_behavior, required_evidence_json,
                 safe_default, status, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    anchor.anchor_id,
                    bundle.bundle_id,
                    canonical_json(anchor.scope),
                    anchor.authoritative_source,
                    canonical_json(anchor.fallback_sources),
                    canonical_json(anchor.forbidden_sources),
                    anchor.freshness_sla_hours,
                    anchor.conflict_behavior,
                    canonical_json(anchor.required_evidence),
                    anchor.safe_default,
                    anchor.status,
                    anchor.description,
                ),
            )
        for invariant in bundle.invariants:
            connection.execute(
                """
                INSERT OR REPLACE INTO authority_invariants
                (invariant_id, bundle_id, summary, severity, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    invariant.invariant_id,
                    bundle.bundle_id,
                    invariant.summary,
                    invariant.severity,
                    invariant.status,
                ),
            )

    return {
        "bundle_id": bundle.bundle_id,
        "bundle_hash": bundle_hash,
        "compiled_at": compiled_at,
        "registry": str(registry_path(root)),
    }


def row_to_anchor(row: sqlite3.Row) -> TruthAnchor:
    return TruthAnchor(
        anchor_id=row["anchor_id"],
        scope=json.loads(row["scope_json"]),
        authoritative_source=row["authoritative_source"],
        fallback_sources=json.loads(row["fallback_sources_json"]),
        forbidden_sources=json.loads(row["forbidden_sources_json"]),
        freshness_sla_hours=int(row["freshness_sla_hours"]),
        conflict_behavior=row["conflict_behavior"],
        required_evidence=json.loads(row["required_evidence_json"]),
        safe_default=row["safe_default"],
        status=row["status"],
        description=row["description"],
    )


def active_bundle(root: Path) -> AuthorityBundle | None:
    try:
        return load_bundle(resolve_active_bundle_path(root))
    except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError):
        return None


def active_bundle_id(root: Path) -> str:
    bundle = active_bundle(root)
    return bundle.bundle_id if bundle else ""


def list_anchors(root: Path, *, active_only: bool = True) -> list[TruthAnchor]:
    bundle_id = active_bundle_id(root) if active_only else ""
    if active_only and not bundle_id:
        return []
    with connect(root) as connection:
        if bundle_id:
            rows = connection.execute(
                "SELECT * FROM authority_anchors WHERE bundle_id = ? ORDER BY anchor_id",
                (bundle_id,),
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM authority_anchors ORDER BY anchor_id").fetchall()
    return [row_to_anchor(row) for row in rows]


def get_anchor(root: Path, anchor_id: str, *, active_only: bool = True) -> TruthAnchor | None:
    bundle_id = active_bundle_id(root) if active_only else ""
    if active_only and not bundle_id:
        return None
    with connect(root) as connection:
        if bundle_id:
            row = connection.execute(
                "SELECT * FROM authority_anchors WHERE anchor_id = ? AND bundle_id = ?",
                (anchor_id, bundle_id),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM authority_anchors WHERE anchor_id = ?",
                (anchor_id,),
            ).fetchone()
    return row_to_anchor(row) if row else None


def active_bundle_record(root: Path) -> dict[str, Any] | None:
    bundle_id = active_bundle_id(root)
    if not bundle_id:
        return None
    with connect(root) as connection:
        row = connection.execute("SELECT * FROM authority_bundles WHERE bundle_id = ?", (bundle_id,)).fetchone()
    return dict(row) if row else None


def verify_registry(root: Path, *, strict: bool = False) -> dict[str, Any]:
    manifest_exists = active_manifest_path(root).exists()
    registry_exists = registry_path(root).exists()
    if not manifest_exists:
        return {"status": "missing", "ok": False, "message": "authority manifest is missing"}
    active_path = resolve_active_bundle_path(root)
    bundle = load_bundle(active_path)
    expected_hash = bundle.bundle_hash()
    if not registry_exists:
        return {
            "status": "missing_registry",
            "ok": not strict,
            "message": "authority registry has not been compiled",
            "expected_hash": expected_hash,
        }
    record = active_bundle_record(root)
    if not record:
        return {
            "status": "empty_registry",
            "ok": not strict,
            "message": "authority registry has no compiled record for the active bundle",
            "expected_hash": expected_hash,
            "bundle_id": bundle.bundle_id,
        }
    actual_hash = record["bundle_hash"]
    ok = actual_hash == expected_hash
    return {
        "status": "ok" if ok else "stale",
        "ok": ok,
        "message": "authority registry is current" if ok else "authority registry is stale; run compile",
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "bundle_id": record["bundle_id"],
    }
