"""Media-type detection for Praxis intake."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import urlparse


EXTENSION_MEDIA_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".rst": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".json": "application/json",
    ".jsonl": "application/jsonl",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}


def extension_for(source_ref: str) -> str:
    parsed = urlparse(source_ref)
    candidate = parsed.path if parsed.scheme else source_ref
    return Path(candidate).suffix.lower()


def normalize_media_type(media_type: str) -> str:
    lowered = (media_type or "").split(";")[0].strip().lower()
    if not lowered:
        return ""
    if lowered in {"text/x-markdown", "text/markdown"}:
        return "text/markdown"
    if lowered in {"application/x-ndjson", "application/jsonl"}:
        return "application/jsonl"
    if "pdf" in lowered:
        return "application/pdf"
    if lowered in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if lowered in {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-powerpoint",
    }:
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if lowered in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if lowered.startswith("image/"):
        return lowered
    if lowered.startswith("audio/"):
        return lowered
    if lowered.startswith("video/"):
        return lowered
    return lowered


def detect_media_type(source_ref: str, *, content_type: str = "") -> str:
    normalized = normalize_media_type(content_type)
    if normalized and normalized != "application/octet-stream":
        return normalized
    extension = extension_for(source_ref)
    if extension in EXTENSION_MEDIA_TYPES:
        return EXTENSION_MEDIA_TYPES[extension]
    guessed, _encoding = mimetypes.guess_type(source_ref)
    return normalize_media_type(guessed or "") or "application/octet-stream"


def media_family(media_type: str) -> str:
    normalized = normalize_media_type(media_type)
    if normalized.startswith("text/"):
        return "text"
    if normalized.startswith("image/"):
        return "image"
    if normalized.startswith("audio/"):
        return "audio"
    if normalized.startswith("video/"):
        return "video"
    if normalized in {"application/json", "application/jsonl"}:
        return "structured"
    if normalized in {
        "application/pdf",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }:
        return "document"
    return "unknown"
