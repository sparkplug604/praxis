"""Archive, export, and guarded deletion for agency client capsules."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from praxis.agency.lifecycle_artifacts import (
    LifecycleTarget,
    assert_safe_target,
    collect_client_targets,
    collect_database_records,
    is_relative_to,
    purge_database_records,
    rel,
)
from praxis.reach.storage import (
    archives_dir,
    client_dir,
    delete_plans_dir,
    deletion_receipts_dir,
    quarantine_dir,
    read_json,
    slug,
    write_json,
)


_rel = rel
_is_relative_to = is_relative_to
LIFECYCLE_ARTIFACT_SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def archive_marker_path(root: Path, client_id: str) -> Path:
    return client_dir(root, client_id) / "archive.json"


def is_archived(root: Path, client_id: str) -> bool:
    if archive_marker_path(root, client_id).exists():
        return True
    permissions_path = client_dir(root, client_id) / "permissions.json"
    if not permissions_path.exists():
        return False
    data = read_json(permissions_path)
    permissions = data.get("permissions", data)
    return permissions.get("lifecycle_status") == "archived"


def archive_client(root: Path, client_id: str, *, reason: str, force: bool = False, dry_run: bool = False) -> dict[str, Any]:
    client_id = slug(client_id)
    capsule_dir = client_dir(root, client_id)
    if not capsule_dir.exists():
        raise KeyError(f"Unknown client capsule: {client_id}")
    marker = archive_marker_path(root, client_id)
    if marker.exists() and not force:
        raise RuntimeError(f"Client {client_id} is already archived. Use --force to update archive metadata.")
    archived_at = utc_now()
    record = {
        "artifact_schema_version": LIFECYCLE_ARTIFACT_SCHEMA_VERSION,
        "client_id": client_id,
        "status": "archived",
        "archived_at": archived_at,
        "reason": reason,
    }
    if dry_run:
        return {**record, "dry_run": True, "would_write": _rel(root, marker)}

    permissions_path = capsule_dir / "permissions.json"
    permissions_payload = read_json(permissions_path) if permissions_path.exists() else {"permissions": {}}
    permissions = dict(permissions_payload.get("permissions", permissions_payload))
    permissions.update(
        {
            "lifecycle_status": "archived",
            "archived_at": archived_at,
            "archive_reason": reason,
        }
    )
    write_json(permissions_path, {"permissions": permissions})
    write_json(marker, record)
    return record


def client_export_exists(root: Path, client_id: str) -> bool:
    if not archives_dir(root).exists():
        return False
    return any(archives_dir(root).glob(f"{slug(client_id)}-*.tar.gz")) or any(archives_dir(root).glob(f"{slug(client_id)}-*.export.json"))


def export_client(root: Path, client_id: str, *, output: Path | None = None, redact: bool = True) -> Path:
    client_id = slug(client_id)
    if not client_dir(root, client_id).exists():
        raise KeyError(f"Unknown client capsule: {client_id}")
    timestamp = _stamp()
    target = output or archives_dir(root) / f"{client_id}-{timestamp}.tar.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    targets = collect_client_targets(root, client_id)
    manifest = {
        "artifact_schema_version": LIFECYCLE_ARTIFACT_SCHEMA_VERSION,
        "exported_at": utc_now(),
        "client_id": client_id,
        "redacted": redact,
        "targets": [item.to_dict(root) for item in targets],
    }
    with tarfile.open(target, "w:gz") as archive:
        _add_json(archive, f"{client_id}/export_manifest.json", manifest)
        for item in targets:
            _add_target(archive, root, item, client_id=client_id, redact=redact)
    write_json(
        archives_dir(root) / f"{client_id}-{timestamp}.export.json",
        {
            "artifact_schema_version": LIFECYCLE_ARTIFACT_SCHEMA_VERSION,
            "client_id": client_id,
            "exported_at": manifest["exported_at"],
            "path": str(target),
            "redacted": redact,
            "target_count": len(targets),
        },
    )
    return target


def create_delete_plan(root: Path, client_id: str, *, reason: str = "", require_archive: bool = True) -> dict[str, Any]:
    client_id = slug(client_id)
    if not client_dir(root, client_id).exists():
        raise KeyError(f"Unknown client capsule: {client_id}")
    targets = collect_client_targets(root, client_id)
    db_records = collect_database_records(root, client_id)
    archive_present = client_export_exists(root, client_id)
    warnings = _delete_warnings(root, client_id, targets, db_records, require_archive=require_archive, archive_present=archive_present)
    material = json.dumps(
        {
            "client_id": client_id,
            "targets": [item.to_dict(root) for item in targets],
            "database_records": db_records,
            "created_at": utc_now(),
        },
        sort_keys=True,
    )
    plan_id = f"del:{client_id}:{_stamp()}:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:10]}"
    plan = {
        "artifact_schema_version": LIFECYCLE_ARTIFACT_SCHEMA_VERSION,
        "plan_id": plan_id,
        "client_id": client_id,
        "status": "planned",
        "created_at": utc_now(),
        "reason": reason,
        "archive_required": require_archive,
        "archive_present": archive_present,
        "targets": [item.to_dict(root) for item in targets],
        "database_records": db_records,
        "warnings": warnings,
        "confirmation_required": {
            "confirm_client": client_id,
            "confirm_delete": "DELETE",
        },
    }
    write_json(delete_plan_path(root, plan_id), plan)
    return plan


def delete_plan_path(root: Path, plan_id: str) -> Path:
    return delete_plans_dir(root) / f"{slug(plan_id)}.json"


def load_delete_plan(root: Path, plan_id: str) -> dict[str, Any]:
    direct = delete_plan_path(root, plan_id)
    if direct.exists():
        return read_json(direct)
    for path in delete_plans_dir(root).glob("*.json"):
        data = read_json(path)
        if data.get("plan_id") == plan_id:
            return data
    raise KeyError(f"Unknown delete plan: {plan_id}")


def delete_client(
    root: Path,
    *,
    plan_id: str,
    confirm_client: str,
    confirm_delete: str,
    no_archive: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    plan = load_delete_plan(root, plan_id)
    client_id = str(plan["client_id"])
    if plan.get("status") == "executed":
        raise RuntimeError(f"Delete plan already executed; receipt_id={plan.get('receipt_id', '')}")
    if confirm_client != client_id:
        raise RuntimeError(f"--confirm-client must exactly match {client_id}.")
    if confirm_delete != "DELETE":
        raise RuntimeError('--confirm-delete must exactly equal "DELETE".')
    if plan.get("archive_required") and not plan.get("archive_present") and not no_archive:
        raise RuntimeError("Deletion requires an archive/export first. Use --no-archive with --reason if this is a privacy deletion.")
    if no_archive and not reason:
        raise RuntimeError("--no-archive requires --reason.")

    receipt_id = f"receipt:{client_id}:{_stamp()}:{hashlib.sha256(plan_id.encode('utf-8')).hexdigest()[:10]}"
    trash_root = quarantine_dir(root) / slug(receipt_id)
    executing_at = utc_now()
    plan["status"] = "executing"
    plan["executing_at"] = executing_at
    write_json(delete_plan_path(root, plan_id), plan)
    moved: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    for item in plan.get("targets", []):
        target = _path_from_plan(root, item)
        assert_safe_target(root, client_id, target, str(item.get("kind") or ""))
        if not target.exists():
            missing.append({"path": _rel(root, target), "reason": str(item.get("reason") or "")})
            continue
        quarantine_path = trash_root / _rel(root, target)
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(quarantine_path))
        moved.append({"from": _rel(root, target), "to": _rel(root, quarantine_path)})

    db_counts = purge_database_records(root, client_id)
    receipt = {
        "artifact_schema_version": LIFECYCLE_ARTIFACT_SCHEMA_VERSION,
        "receipt_id": receipt_id,
        "plan_id": plan_id,
        "client_id": client_id,
        "deleted_at": utc_now(),
        "status": "quarantined",
        "reason": reason or plan.get("reason", ""),
        "archive_present": bool(plan.get("archive_present")),
        "no_archive": no_archive,
        "moved": moved,
        "missing": missing,
        "database_records_removed": db_counts,
        "quarantine_path": _rel(root, trash_root),
        "confirmation": {
            "confirm_client": confirm_client,
            "confirm_delete": confirm_delete,
        },
        "note": "Local files were moved to quarantine. Use purge to permanently remove the quarantine folder.",
        "resume_hint": "If deletion was interrupted, inspect this receipt and the matching delete plan before retrying purge or deletion.",
    }
    write_json(deletion_receipt_path(root, receipt_id), receipt)
    plan["status"] = "executed"
    plan["receipt_id"] = receipt_id
    plan["executed_at"] = receipt["deleted_at"]
    write_json(delete_plan_path(root, plan_id), plan)
    return receipt


def deletion_receipt_path(root: Path, receipt_id: str) -> Path:
    return deletion_receipts_dir(root) / f"{slug(receipt_id)}.json"


def load_deletion_receipt(root: Path, receipt_id: str) -> dict[str, Any]:
    direct = deletion_receipt_path(root, receipt_id)
    if direct.exists():
        return read_json(direct)
    for path in deletion_receipts_dir(root).glob("*.json"):
        data = read_json(path)
        if data.get("receipt_id") == receipt_id:
            return data
    raise KeyError(f"Unknown deletion receipt: {receipt_id}")


def purge_quarantine(root: Path, *, receipt_id: str, confirm_delete: str) -> dict[str, Any]:
    if confirm_delete != "PURGE":
        raise RuntimeError('--confirm-delete must exactly equal "PURGE".')
    receipt = load_deletion_receipt(root, receipt_id)
    trash_path = root / str(receipt.get("quarantine_path") or "")
    if not _is_relative_to(trash_path.resolve(), quarantine_dir(root).resolve()):
        raise RuntimeError("Receipt quarantine path is outside Praxis quarantine.")
    if trash_path.exists():
        shutil.rmtree(trash_path)
    receipt["status"] = "purged"
    receipt["purged_at"] = utc_now()
    write_json(deletion_receipt_path(root, receipt_id), receipt)
    return receipt


def _delete_warnings(
    root: Path,
    client_id: str,
    targets: list[LifecycleTarget],
    db_records: dict[str, Any],
    *,
    require_archive: bool,
    archive_present: bool,
) -> list[str]:
    warnings = [
        "Praxis deletion only removes local Praxis artifacts. It does not delete records from CRM, ads, analytics, or other source systems.",
        "Review the target list before executing deletion.",
    ]
    if require_archive and not archive_present:
        warnings.append("No local client export/archive was found. Deletion will be refused unless --no-archive and --reason are provided.")
    if not is_archived(root, client_id):
        warnings.append("Client is not archived yet. Consider archiving before deletion unless this is an immediate privacy request.")
    if any(item.reason == "Reach evidence card" for item in targets):
        warnings.append("Reach evidence cards for this client will be quarantined.")
    if any(item.reason == "Reach conflict record" for item in targets):
        warnings.append("Reach conflict records for this client will be quarantined.")
    if db_records.get("source_ids"):
        warnings.append("Praxis Core source and vector records generated from Reach evidence will be removed from local databases.")
    return warnings


def _path_from_plan(root: Path, item: dict[str, Any]) -> Path:
    rel = str(item.get("path") or "")
    if not rel:
        raise RuntimeError("Delete plan target is missing path.")
    path = (root / rel).resolve()
    if not _is_relative_to(path, root.resolve()):
        raise RuntimeError(f"Delete plan target escapes Praxis root: {rel}")
    return path


def _add_target(archive: tarfile.TarFile, root: Path, item: LifecycleTarget, *, client_id: str, redact: bool) -> None:
    path = item.path
    arcname = f"{client_id}/{_rel(root, path)}"
    if path.is_dir():
        for child in sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink()):
            child_arcname = f"{client_id}/{_rel(root, child)}"
            _add_file(archive, child, child_arcname, redact=redact)
    elif path.is_file() and not path.is_symlink():
        _add_file(archive, path, arcname, redact=redact)


def _add_file(archive: tarfile.TarFile, path: Path, arcname: str, *, redact: bool) -> None:
    if redact and path.suffix.lower() == ".json":
        try:
            data = _redact_json(read_json(path))
        except json.JSONDecodeError:
            archive.add(path, arcname=arcname)
            return
        _add_json(archive, arcname, data)
        return
    archive.add(path, arcname=arcname)


def _add_json(archive: tarfile.TarFile, arcname: str, data: dict[str, Any]) -> None:
    raw = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    info = tarfile.TarInfo(arcname)
    info.size = len(raw)
    archive.addfile(info, io.BytesIO(raw))


def _redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ["token", "secret", "password", "credential"]):
                if lowered.endswith("_env") or lowered in {"credential_env", "fallback_credential_env"}:
                    out[key] = item
                else:
                    out[key] = "[REDACTED]"
            else:
                out[key] = _redact_json(item)
        return out
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    return value


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
