"""Converter registry and source extraction orchestration."""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .converters import (
    CONVERTER_VERSION,
    convert_audio,
    convert_csv,
    convert_docx,
    convert_html,
    convert_image,
    convert_json,
    convert_markdown,
    convert_pdf,
    convert_pptx,
    convert_ocr_sidecar,
    convert_text,
    convert_transcript_sidecar,
    convert_video,
    convert_xlsx,
    sha256_bytes,
    sha256_text,
)
from .detect import detect_media_type, media_family
from .media import faster_whisper_status, optional_package_status, tool_status
from .models import ExtractionResult, IntakeError, UnsupportedMediaError
from .quality import score_parse_quality


USER_AGENT = "PraxisIntake/0.1 (+local source conversion)"
Converter = Callable[[str, bytes, dict[str, Any]], tuple[list, dict[str, Any], list[str]]]


@dataclass(frozen=True)
class ConverterSpec:
    name: str
    media_types: tuple[str, ...]
    function: Converter
    status: str = "available"
    notes: str = ""


CONVERTERS: tuple[ConverterSpec, ...] = (
    ConverterSpec("text", ("text/plain", "application/octet-stream"), convert_text),
    ConverterSpec("markdown", ("text/markdown",), convert_markdown),
    ConverterSpec("html", ("text/html",), convert_html),
    ConverterSpec("pdf-pypdf", ("application/pdf",), convert_pdf, notes="Requires optional dependency: pypdf."),
    ConverterSpec("csv", ("text/csv",), convert_csv),
    ConverterSpec("json", ("application/json", "application/jsonl"), convert_json),
    ConverterSpec("docx-office", ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",), convert_docx, notes="Uses MarkItDown when installed, otherwise basic ZIP/XML extraction."),
    ConverterSpec("pptx-office", ("application/vnd.openxmlformats-officedocument.presentationml.presentation",), convert_pptx, notes="Uses MarkItDown when installed, otherwise basic ZIP/XML extraction."),
    ConverterSpec("xlsx-office", ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",), convert_xlsx, notes="Uses MarkItDown when installed, otherwise basic ZIP/XML extraction."),
    ConverterSpec("image-ocr", ("image/png", "image/jpeg", "image/webp", "image/gif"), convert_image, notes="Uses OCR sidecars when present; direct OCR requires Pillow and pytesseract."),
    ConverterSpec("audio-transcript", ("audio/mpeg", "audio/wav", "audio/mp4"), convert_audio, status="media_metadata_available", notes="Uses transcript sidecars when present; optional direct speech-to-text requires praxis-ktos[intake-stt]."),
    ConverterSpec("video-transcript", ("video/mp4", "video/quicktime", "video/webm"), convert_video, status="media_metadata_available", notes="Uses transcript sidecars when present; optional direct speech-to-text requires praxis-ktos[intake-stt]."),
)


def converter_for(media_type: str) -> ConverterSpec | None:
    for spec in CONVERTERS:
        if media_type in spec.media_types:
            return spec
    family = media_family(media_type)
    if family == "image":
        return next(spec for spec in CONVERTERS if spec.name == "image-ocr")
    if family == "audio":
        return next(spec for spec in CONVERTERS if spec.name == "audio-transcript")
    if family == "video":
        return next(spec for spec in CONVERTERS if spec.name == "video-transcript")
    return None


def build_result(
    *,
    source_ref: str,
    media_type: str,
    converter_name: str,
    body: bytes,
    units: list,
    metadata: dict[str, Any],
    warnings: list[str],
) -> ExtractionResult:
    text = "\n\n".join(unit.display_text() for unit in units if unit.display_text())
    result = ExtractionResult(
        source_ref=source_ref,
        media_type=media_type,
        converter_name=converter_name,
        converter_version=CONVERTER_VERSION,
        content_hash=sha256_text(text),
        artifact_hash=sha256_bytes(body),
        artifact_bytes=body,
        units=units,
        metadata=metadata,
        warnings=warnings,
    )
    result.parse_quality = score_parse_quality(media_type=media_type, units=units, warnings=warnings, metadata=metadata)
    return result


def convert_bytes(source_ref: str, body: bytes, *, media_type: str = "", metadata: dict[str, Any] | None = None) -> ExtractionResult:
    metadata = dict(metadata or {})
    resolved_media_type = detect_media_type(source_ref, content_type=media_type)
    spec = converter_for(resolved_media_type)
    if spec is None:
        raise UnsupportedMediaError(f"No Praxis intake converter for media type: {resolved_media_type}")
    units, converter_metadata, warnings = spec.function(source_ref, body, {**metadata, "media_type": resolved_media_type})
    converter_name = str(converter_metadata.pop("_converter_name", spec.name))
    return build_result(
        source_ref=source_ref,
        media_type=resolved_media_type,
        converter_name=converter_name,
        body=body,
        units=units,
        metadata=converter_metadata,
        warnings=warnings,
    )


def _fetch_url(url: str, *, timeout: int = 20) -> tuple[bytes, dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return body, {
                "url": url,
                "content_type": response.headers.get("content-type", ""),
                "status": getattr(response, "status", None),
                "final_url": response.geturl(),
            }
    except urllib.error.URLError as exc:
        raise IntakeError(f"Could not fetch {url}: {exc}") from exc


def _candidate_files(root: Path) -> list[Path]:
    names = {
        "README.md", "README.rst", "README.txt", "pyproject.toml", "package.json",
        "CHANGELOG.md", "docs/index.md", "docs/quickstart.md", "docs/getting-started.md",
        "docs/concepts/how-it-works.md", "NON-GOALS.md", "SECURITY.md",
    }
    files: list[Path] = []
    for name in sorted(names):
        path = root / name
        if path.exists() and path.is_file():
            files.append(path)
    if len(files) < 12 and (root / "docs").exists():
        for path in sorted((root / "docs").glob("**/*.md"))[:20]:
            if path not in files:
                files.append(path)
    return files[:28]


def _extract_file(path: Path, metadata: dict[str, Any] | None = None) -> ExtractionResult:
    extra_metadata = dict(metadata or {})
    body = path.read_bytes()
    media_type = detect_media_type(str(path))
    sidecar = sidecar_for(path, media_type)
    if sidecar:
        sidecar_text = sidecar.read_text(encoding="utf-8", errors="replace")
        metadata = {**extra_metadata, "path": str(path), "kind": "file", "sidecar_path": str(sidecar)}
        family = media_family(media_type)
        if family in {"audio", "video"}:
            units, converter_metadata, warnings = convert_transcript_sidecar(
                str(path),
                sidecar_text,
                {**metadata, "media_type": media_type},
                media_kind=family,
                sidecar_path=str(sidecar),
            )
            return build_result(
                source_ref=str(path),
                media_type=media_type,
                converter_name=f"{family}-transcript-sidecar",
                body=body + sidecar_text.encode("utf-8"),
                units=units,
                metadata=converter_metadata,
                warnings=warnings,
            )
        if family == "image":
            units, converter_metadata, warnings = convert_ocr_sidecar(
                str(path),
                sidecar_text,
                {**metadata, "media_type": media_type},
                sidecar_path=str(sidecar),
            )
            return build_result(
                source_ref=str(path),
                media_type=media_type,
                converter_name="image-ocr-sidecar",
                body=body + sidecar_text.encode("utf-8"),
                units=units,
                metadata=converter_metadata,
                warnings=warnings,
            )
    return convert_bytes(str(path), body, media_type=media_type, metadata={**extra_metadata, "path": str(path), "kind": "file"})


def sidecar_for(path: Path, media_type: str) -> Path | None:
    family = media_family(media_type)
    if family not in {"audio", "video", "image"}:
        return None
    if family == "image":
        suffixes = [".ocr.txt", ".alt.txt", ".transcript.txt", ".txt", ".md"]
    else:
        suffixes = [".transcript.vtt", ".transcript.srt", ".transcript.txt", ".vtt", ".srt", ".txt", ".md"]
    stem = path.with_suffix("")
    candidates: list[Path] = []
    for suffix in suffixes:
        candidates.append(Path(str(path) + suffix))
        candidates.append(stem.with_suffix(suffix))
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _extract_directory(path: Path) -> ExtractionResult:
    units = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {"path": str(path), "kind": "directory", "files": []}
    body_hash_parts: list[str] = []
    for file_path in _candidate_files(path):
        try:
            result = _extract_file(file_path)
        except IntakeError as exc:
            warnings.append(f"skipped:{file_path.relative_to(path)}:{exc}")
            continue
        metadata["files"].append(str(file_path.relative_to(path)))
        body_hash_parts.append(result.artifact_hash)
        for unit in result.units:
            unit.location = {"file": str(file_path.relative_to(path)), **unit.location}
            units.append(unit)
    if not units:
        listing = "\n".join(str(p.relative_to(path)) for p in sorted(path.rglob("*"))[:200])
        body = listing.encode("utf-8")
        result = convert_bytes(str(path), body, media_type="text/plain", metadata=metadata)
        result.warnings.append("directory_had_no_supported_capture_files; captured listing only")
        result.parse_quality = score_parse_quality(media_type=result.media_type, units=result.units, warnings=result.warnings, metadata=result.metadata)
        return result
    combined_text = "\n".join(unit.display_text() for unit in units)
    synthetic_body = ("\n".join(body_hash_parts) + "\n" + combined_text[:10000]).encode("utf-8")
    result = build_result(
        source_ref=str(path),
        media_type="inode/directory",
        converter_name="directory",
        body=synthetic_body,
        units=units,
        metadata=metadata,
        warnings=warnings,
    )
    return result


def extract_source(source: str, *, metadata: dict[str, Any] | None = None) -> ExtractionResult:
    metadata = dict(metadata or {})
    if source.startswith(("http://", "https://")):
        body, fetch_metadata = _fetch_url(source)
        media_type = detect_media_type(fetch_metadata.get("final_url") or source, content_type=fetch_metadata.get("content_type", ""))
        return convert_bytes(source, body, media_type=media_type, metadata={**metadata, **fetch_metadata})
    path = Path(source).expanduser()
    if path.is_file():
        return _extract_file(path, metadata=metadata)
    if path.is_dir():
        return _extract_directory(path)
    raise FileNotFoundError(f"Local source not found: {source}")


def inspect_source(source: str) -> dict[str, Any]:
    if source.startswith(("http://", "https://")):
        return {"source": source, "kind": "url", "media_type": "unknown_until_fetch", "converter": "fetch-required"}
    path = Path(source).expanduser()
    if not path.exists():
        return {"source": source, "kind": "missing", "status": "not_found"}
    if path.is_dir():
        return {"source": str(path), "kind": "directory", "media_type": "inode/directory", "converter": "directory"}
    media_type = detect_media_type(str(path))
    spec = converter_for(media_type)
    return {
        "source": str(path),
        "kind": "file",
        "media_type": media_type,
        "converter": sidecar_converter(path, media_type) or (spec.name if spec else ""),
        "converter_status": spec.status if spec else "unsupported",
        "notes": spec.notes if spec else "",
    }


def sidecar_converter(path: Path, media_type: str) -> str:
    sidecar = sidecar_for(path, media_type)
    if not sidecar:
        return ""
    family = media_family(media_type)
    if family in {"audio", "video"}:
        return f"{family}-transcript-sidecar"
    if family == "image":
        return "image-ocr-sidecar"
    return ""


def converter_doctor() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in CONVERTERS:
        status = spec.status
        detail = spec.notes
        if spec.name == "pdf-pypdf":
            try:
                import pypdf  # noqa: F401
            except Exception:
                status = "missing_optional_dependency"
                detail = "Install with: python3 -m pip install 'praxis-ktos[intake-basic]'"
        if spec.name == "image-ocr":
            try:
                import PIL  # noqa: F401
                import pytesseract  # noqa: F401
            except Exception:
                status = "sidecar_available_dependency_missing"
                detail = "OCR sidecars are supported; install Pillow/pytesseract and system OCR for direct image OCR."
        if spec.name in {"docx-office", "pptx-office", "xlsx-office"}:
            try:
                import markitdown  # noqa: F401
                detail = "MarkItDown available; basic fallback remains available."
            except Exception:
                status = "available_basic_fallback"
                detail = "Install markitdown for stronger Office conversion; basic ZIP/XML fallback is available."
        rows.append({"converter": spec.name, "media_types": list(spec.media_types), "status": status, "notes": detail})
    for tool in ("ffprobe", "ffmpeg"):
        status = tool_status(tool)
        notes = status["path"] or "Install FFmpeg for media probing/transcription workflows."
        rows.append({"converter": f"media-{tool}", "media_types": ["audio/*", "video/*"], "status": status["status"], "notes": notes})
    stt = faster_whisper_status()
    rows.append({"converter": stt["converter"], "media_types": ["audio/*", "video/*"], "status": stt["status"], "notes": stt["notes"]})
    rows.append({"converter": "keyframes-ffmpeg", "media_types": ["video/*"], "status": tool_status("ffmpeg")["status"], "notes": tool_status("ffmpeg")["path"] or "Install FFmpeg for interval/manual keyframe extraction."})
    scene = optional_package_status("scenedetect", converter="keyframes-scenedetect", notes="Install scenedetect for scene-aware keyframe extraction.")
    rows.append({"converter": scene["converter"], "media_types": ["video/*"], "status": scene["status"], "notes": scene["notes"]})
    diarization = optional_package_status("pyannote.audio", converter="diarization-pyannote", notes="Install pyannote.audio and configure model access for speaker diarization.")
    rows.append({"converter": diarization["converter"], "media_types": ["audio/*", "video/*"], "status": diarization["status"], "notes": diarization["notes"]})
    visual = optional_package_status("open_clip", converter="visual-openclip", notes="Install open_clip_torch/torch for visual embeddings.")
    rows.append({"converter": visual["converter"], "media_types": ["image/*", "video/*"], "status": visual["status"], "notes": visual["notes"]})
    return rows
