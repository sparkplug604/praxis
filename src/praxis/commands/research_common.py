"""Shared helpers for Praxis research ingest scripts."""

from __future__ import annotations

import datetime as _dt
import hashlib
import html.parser
import io
import json
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from praxis.paths import default_root


DEFAULT_ROOT = default_root()
DEFAULT_DB = DEFAULT_ROOT / "kg" / "skill_graph.sqlite"
USER_AGENT = "PraxisResearch/0.1 (+local research pipeline)"


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


class _HTMLTextExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        raw = " ".join(self.parts)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s+", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def html_to_text(raw: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw)
    return parser.text()


def pdf_to_text(body: bytes) -> tuple[str, dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - depends on optional bundled runtime
        raise RuntimeError("PDF capture requires pypdf. Install pypdf or run with a Python runtime that includes it.") from exc

    reader = PdfReader(io.BytesIO(body))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, 1):
        extracted = page.extract_text() or ""
        if extracted.strip():
            pages.append(f"\n\n## Page {index}\n\n{extracted.strip()}")
    return "\n".join(pages).strip(), {"pdf_pages": len(reader.pages)}


def read_web(url: str, *, timeout: int = 20) -> tuple[str, dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "")
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read()
            metadata = {
                "url": url,
                "content_type": content_type,
                "status": getattr(response, "status", None),
                "final_url": response.geturl(),
            }
            if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
                text, pdf_metadata = pdf_to_text(body)
                return text, {**metadata, **pdf_metadata}
            decoded = body.decode(charset, errors="replace")
            text = html_to_text(decoded) if "html" in content_type.lower() else decoded
            return text, metadata
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not fetch {url}: {exc}") from exc


def _candidate_files(root: Path) -> list[Path]:
    names = {
        "README.md", "README.rst", "README.txt", "pyproject.toml", "package.json",
        "CHANGELOG.md", "docs/index.md", "docs/quickstart.md", "docs/getting-started.md",
        "docs/concepts/how-it-works.md", "NON-GOALS.md", "SECURITY.md",
    }
    files: list[Path] = []
    for name in names:
        path = root / name
        if path.exists() and path.is_file():
            files.append(path)
    if len(files) < 12:
        for path in sorted((root / "docs").glob("**/*.md"))[:20] if (root / "docs").exists() else []:
            if path not in files:
                files.append(path)
    return files[:28]


def read_local(source: Path) -> tuple[str, dict[str, Any]]:
    if source.is_file():
        text = source.read_text(encoding="utf-8", errors="replace")
        return text, {"path": str(source), "kind": "file"}
    if source.is_dir():
        chunks: list[str] = [f"# Local directory capture: {source}\n"]
        files = _candidate_files(source)
        for path in files:
            rel = path.relative_to(source)
            chunks.append(f"\n\n## File: {rel}\n")
            chunks.append(path.read_text(encoding="utf-8", errors="replace")[:50000])
        if not files:
            listing = "\n".join(str(p.relative_to(source)) for p in sorted(source.rglob("*"))[:200])
            chunks.append("\n\n## File listing\n")
            chunks.append(listing)
        return "".join(chunks), {"path": str(source), "kind": "directory", "files": [str(p.relative_to(source)) for p in files]}
    raise FileNotFoundError(f"Local source not found: {source}")


def read_source(source: str) -> tuple[str, dict[str, Any]]:
    if source.startswith(("http://", "https://")):
        return read_web(source)
    return read_local(Path(source).expanduser())


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
