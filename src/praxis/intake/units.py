"""Shared source-evidence unit helpers for Praxis intake."""

from __future__ import annotations

import hashlib
from typing import Any

from .models import ExtractedUnit


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unit_id(source_ref: str, unit_type: str, index: int, text: str) -> str:
    digest = hashlib.sha1(f"{source_ref}\0{unit_type}\0{index}\0{text[:160]}".encode("utf-8")).hexdigest()[:12]
    return f"unit:{unit_type}:{digest}"


def make_unit(
    source_ref: str,
    unit_type: str,
    text: str,
    *,
    index: int = 1,
    markdown: str = "",
    structured_data: dict[str, Any] | None = None,
    location: dict[str, Any] | None = None,
    parent_unit_id: str = "",
    confidence: str = "medium",
    warnings: list[str] | None = None,
) -> ExtractedUnit:
    return ExtractedUnit(
        unit_id=unit_id(source_ref, unit_type, index, text),
        unit_type=unit_type,
        text=text.strip(),
        markdown=(markdown or text).strip(),
        structured_data=structured_data or {},
        location=location or {},
        parent_unit_id=parent_unit_id,
        source_ref=source_ref,
        confidence=confidence,
        warnings=warnings or [],
    )


def media_evidence_metadata(
    *,
    adapter_name: str = "",
    model_name: str = "",
    lifecycle: str = "derived",
    confidence_reason: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Common metadata for media-derived evidence units."""

    data = {
        "evidence_lifecycle": lifecycle,
        "adapter_name": adapter_name,
        "model_name": model_name,
        "confidence_reason": confidence_reason,
    }
    if extra:
        data.update(extra)
    return {key: value for key, value in data.items() if value is not None and value != "" and value != []}
