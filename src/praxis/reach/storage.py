"""Filesystem storage helpers for Praxis Reach artifacts."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from praxis.paths import agency_dir as praxis_agency_dir
from praxis.paths import reach_dir as praxis_reach_dir

try:  # pragma: no cover - exercised on Unix in CI/local development.
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback.
    fcntl = None
    import msvcrt


def slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return cleaned or "item"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@contextlib.contextmanager
def file_lock(path: Path):
    """Process-local filesystem lock used around mutable Reach artifacts."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        _lock_file(lock_file)
        try:
            yield
        finally:
            _unlock_file(lock_file)


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write JSON so interrupted runs do not leave torn files."""

    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    write_text_atomic(path, payload)


def write_text_atomic(path: Path, text: str) -> None:
    """Atomically write text content with the same lock discipline as JSON."""

    with file_lock(path):
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(text)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


def _lock_file(lock_file) -> None:
    if fcntl is not None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        return
    lock_file.seek(0)
    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)


def _unlock_file(lock_file) -> None:
    if fcntl is not None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return
    lock_file.seek(0)
    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


def reach_dir(root: Path) -> Path:
    return praxis_reach_dir(root)


def agency_dir(root: Path) -> Path:
    return praxis_agency_dir(root)


def lifecycle_dir(root: Path) -> Path:
    return agency_dir(root) / "lifecycle"


def archives_dir(root: Path) -> Path:
    return lifecycle_dir(root) / "archives"


def delete_plans_dir(root: Path) -> Path:
    return lifecycle_dir(root) / "delete_plans"


def deletion_receipts_dir(root: Path) -> Path:
    return lifecycle_dir(root) / "deletion_receipts"


def quarantine_dir(root: Path) -> Path:
    return lifecycle_dir(root) / "quarantine"


def manifests_dir(root: Path) -> Path:
    return reach_dir(root) / "query_manifests"


def ontology_dir(root: Path) -> Path:
    return reach_dir(root) / "ontology"


def evidence_dir(root: Path) -> Path:
    return reach_dir(root) / "evidence"


def reach_conflicts_dir(root: Path) -> Path:
    return reach_dir(root) / "conflicts"


def context_dir(root: Path) -> Path:
    return reach_dir(root) / "context_packs"


def fixtures_dir(root: Path) -> Path:
    return reach_dir(root) / "fixtures"


def client_dir(root: Path, client_id: str) -> Path:
    return agency_dir(root) / "clients" / slug(client_id)


def client_capsule_path(root: Path, client_id: str) -> Path:
    return client_dir(root, client_id) / "client.json"


def client_systems_path(root: Path, client_id: str) -> Path:
    return client_dir(root, client_id) / "systems.json"


def client_field_map_path(root: Path, client_id: str) -> Path:
    return client_dir(root, client_id) / "field_map.json"


def client_metrics_path(root: Path, client_id: str) -> Path:
    return client_dir(root, client_id) / "metrics.json"


def client_permissions_path(root: Path, client_id: str) -> Path:
    return client_dir(root, client_id) / "permissions.json"


def ensure_reach_workspace(root: Path) -> None:
    for path in [
        manifests_dir(root),
        ontology_dir(root),
        evidence_dir(root),
        reach_conflicts_dir(root),
        context_dir(root),
        fixtures_dir(root),
        agency_dir(root) / "clients",
        archives_dir(root),
        delete_plans_dir(root),
        deletion_receipts_dir(root),
        quarantine_dir(root),
    ]:
        path.mkdir(parents=True, exist_ok=True)
