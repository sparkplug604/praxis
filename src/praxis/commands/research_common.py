"""Shared helpers for Praxis research ingest scripts."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from praxis.paths import default_root, kg_dir
from praxis.intake import extract_source
from praxis.intake.converters import convert_pdf as _convert_pdf
from praxis.intake.converters import html_to_text as _html_to_text


DEFAULT_ROOT = default_root()
DEFAULT_DB = kg_dir(DEFAULT_ROOT) / "skill_graph.sqlite"


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slug(text: str, *, max_len: int = 80) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"https?://", "", lowered)
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = lowered.strip("-")
    if not lowered:
        lowered = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return lowered[:max_len].strip("-") or hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def html_to_text(raw: str) -> str:
    return _html_to_text(raw)


def pdf_to_text(body: bytes) -> tuple[str, dict[str, Any]]:
    units, metadata, warnings = _convert_pdf("inline.pdf", body, {})
    text = "\n\n".join(unit.display_text() for unit in units if unit.display_text())
    return text, {**metadata, "intake_warnings": warnings}


def read_web(url: str, *, timeout: int = 20) -> tuple[str, dict[str, Any]]:
    return extract_source(url).to_legacy()


def read_local(source: Path) -> tuple[str, dict[str, Any]]:
    return extract_source(str(source)).to_legacy()


def read_source(source: str) -> tuple[str, dict[str, Any]]:
    return extract_source(source).to_legacy()


def read_source_extraction(source: str):
    return extract_source(source)


def infer_source_type(source: str, text: str) -> str:
    lowered = source.lower()
    sample = text[:5000].lower()
    if "github.com" in lowered or "pyproject.toml" in sample or "package.json" in sample:
        return "repo"
    if "pypi.org/project" in lowered or "npmjs.com/package" in lowered:
        return "package"
    if "arxiv.org" in lowered or "doi.org" in lowered:
        return "paper"
    if "/docs" in lowered or "documentation" in sample:
        return "docs"
    if lowered.startswith(("http://", "https://")):
        return "web"
    return "local"


def credibility_score(source_type: str, metadata: dict[str, Any]) -> int:
    if source_type in {"repo", "package", "paper", "docs"}:
        return 4
    if source_type == "local":
        return 3
    return 2


def title_from_source(source: str, text: str) -> str:
    for line in text.splitlines()[:80]:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("#").strip()
    if source.startswith(("http://", "https://")):
        return source.rstrip("/").split("/")[-1] or source
    return Path(source).expanduser().name


def summarize_text(text: str, *, max_chars: int = 1800) -> str:
    cleaned = re.sub(r"\n{3,}", "\n\n", text.strip())
    paragraphs = [p.strip() for p in cleaned.split("\n\n") if len(p.strip()) > 40]
    selected = paragraphs[:6] if paragraphs else [cleaned[:max_chars]]
    summary = "\n\n".join(selected)
    return summary[:max_chars].strip()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def register_source(
    connection: sqlite3.Connection,
    *,
    source_id: str,
    url: str,
    title: str,
    source_type: str,
    canonical_ref: str,
    freshness_window_days: int,
    credibility: int,
    notes: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO source_registry(
          id, url, title, source_type, canonical_ref, freshness_window_days,
          status, credibility_score, notes, metadata_json, last_checked_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          url=excluded.url,
          title=excluded.title,
          source_type=excluded.source_type,
          canonical_ref=excluded.canonical_ref,
          freshness_window_days=excluded.freshness_window_days,
          credibility_score=excluded.credibility_score,
          notes=excluded.notes,
          metadata_json=excluded.metadata_json,
          last_checked_at=excluded.last_checked_at,
          updated_at=CURRENT_TIMESTAMP
        """,
        (
            source_id,
            url,
            title,
            source_type,
            canonical_ref,
            freshness_window_days,
            credibility,
            notes,
            json.dumps(metadata or {}, sort_keys=True),
            utc_now(),
        ),
    )


def register_capture(
    connection: sqlite3.Connection,
    *,
    capture_id: str,
    source_id: str,
    content_hash: str,
    raw_path: str,
    summary_path: str,
    metadata: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO source_captures(
          id, source_id, content_hash, raw_path, summary_path, extraction_status, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, 'captured', ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (capture_id, source_id, content_hash, raw_path, summary_path, json.dumps(metadata, sort_keys=True)),
    )
    connection.execute(
        """
        UPDATE source_registry
        SET current_capture_id = ?, last_checked_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (capture_id, utc_now(), source_id),
    )
