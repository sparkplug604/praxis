"""Cache helpers for expensive Praxis media intake artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .media_models import TranscriptResult


MEDIA_HELPER_VERSION = "1"


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def artifact_cache_root(kind: str) -> Path | None:
    root = os.environ.get("PRAXIS_ROOT")
    if not root:
        return None
    path = Path(root) / "intake" / "cache"
    return path / kind if kind else path


def cache_key(body: bytes, model_name: str, options: dict[str, Any]) -> str:
    public_options = {key: value for key, value in options.items() if not key.startswith("_")}
    payload = json.dumps({"model": model_name, "options": public_options}, sort_keys=True, default=str)
    return hashlib.sha256((sha256_bytes(body) + "\0" + payload).encode("utf-8")).hexdigest()


def transcript_cache_root() -> Path | None:
    return artifact_cache_root("transcripts")


def read_cached_transcript(body: bytes, model_name: str, options: dict[str, Any]) -> TranscriptResult | None:
    root = transcript_cache_root()
    if root is None:
        return None
    path = root / f"{cache_key(body, model_name, options)}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    metadata = dict(data.get("metadata") or {})
    metadata["transcript_cache_path"] = str(path)
    metadata["transcript_cache_status"] = "hit"
    return TranscriptResult(
        text=str(data.get("text") or ""),
        metadata=metadata,
        warnings=list(data.get("warnings") or []) + ["transcript_cache_hit"],
    )


def write_cached_transcript(body: bytes, model_name: str, options: dict[str, Any], transcript: TranscriptResult) -> TranscriptResult:
    root = transcript_cache_root()
    if root is None:
        transcript.warnings.append("transcript_cache_unavailable_no_praxis_root")
        return transcript
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{cache_key(body, model_name, options)}.json"
    metadata = {**transcript.metadata, "transcript_cache_path": str(path), "transcript_cache_status": "stored"}
    path.write_text(
        json.dumps(
            {
                "media_helper_version": MEDIA_HELPER_VERSION,
                "model": model_name,
                "text": transcript.text,
                "metadata": metadata,
                "warnings": transcript.warnings,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    transcript.metadata = metadata
    return transcript


def cache_entries(root: Path | None = None) -> list[dict[str, Any]]:
    root = root or artifact_cache_root("") or (Path(tempfile.gettempdir()) / "praxis-intake")
    entries: list[dict[str, Any]] = []
    for kind in ("transcripts", "keyframes"):
        cache_root = root / kind
        if not cache_root.exists():
            continue
        if kind == "transcripts":
            for path in sorted(cache_root.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    data = {}
                entries.append(
                    {
                        "kind": kind,
                        "id": path.stem,
                        "path": str(path),
                        "model": data.get("model", ""),
                        "text_chars": len(str(data.get("text") or "")),
                        "warnings": data.get("warnings") or [],
                    }
                )
        if kind == "keyframes":
            for manifest in sorted(cache_root.glob("*/manifest.json")):
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    data = {}
                entries.append(
                    {
                        "kind": kind,
                        "id": manifest.parent.name,
                        "path": str(manifest),
                        "keyframe_count": len(data.get("keyframes") or []),
                        "scene_count": len(data.get("scenes") or []),
                        "warnings": data.get("warnings") or [],
                    }
                )
    return entries


def cache_entry(root: Path, entry_id: str) -> dict[str, Any] | None:
    for entry in cache_entries(root):
        if entry["id"] == entry_id:
            path = Path(entry["path"])
            try:
                return {"entry": entry, "data": json.loads(path.read_text(encoding="utf-8"))}
            except json.JSONDecodeError:
                return {"entry": entry, "data": {}}
    return None


def clear_cache(root: Path, *, kind: str = "", entry_id: str = "") -> int:
    deleted = 0
    for entry in cache_entries(root):
        if kind and entry["kind"] != kind:
            continue
        if entry_id and entry["id"] != entry_id:
            continue
        path = Path(entry["path"])
        target = path.parent if entry["kind"] == "keyframes" else path
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            deleted += 1
    return deleted
