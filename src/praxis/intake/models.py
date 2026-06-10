"""Data contracts for Praxis source intake."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class IntakeError(RuntimeError):
    """Base error for source intake failures."""


class MissingDependencyError(IntakeError):
    """Raised when a detected source needs an optional parser dependency."""


class UnsupportedMediaError(IntakeError):
    """Raised when Praxis detects a source it cannot convert yet."""


@dataclass
class ParseQuality:
    """Machine-readable confidence about conversion quality."""

    score: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(max(0.0, min(1.0, self.score)), 4),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


@dataclass
class ExtractedUnit:
    """A normalized piece of source evidence produced by a converter."""

    unit_id: str
    unit_type: str
    text: str
    markdown: str = ""
    structured_data: dict[str, Any] = field(default_factory=dict)
    location: dict[str, Any] = field(default_factory=dict)
    parent_unit_id: str = ""
    source_ref: str = ""
    confidence: str = "medium"
    warnings: list[str] = field(default_factory=list)

    def display_text(self) -> str:
        return (self.markdown or self.text).strip()

    def to_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "unit_id": self.unit_id,
            "unit_type": self.unit_type,
            "structured_data": self.structured_data,
            "location": self.location,
            "parent_unit_id": self.parent_unit_id,
            "source_ref": self.source_ref,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }
        if include_text:
            data["text"] = self.text
            data["markdown"] = self.markdown
        return data


@dataclass
class ExtractionResult:
    """Normalized converter output consumed by capture, chunking, and search."""

    source_ref: str
    media_type: str
    converter_name: str
    converter_version: str
    content_hash: str
    artifact_hash: str = ""
    artifact_bytes: bytes | None = field(default=None, repr=False)
    units: list[ExtractedUnit] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    parse_quality: ParseQuality = field(default_factory=lambda: ParseQuality(score=0.0))

    @property
    def text(self) -> str:
        parts = [unit.display_text() for unit in self.units if unit.display_text()]
        return "\n\n".join(parts).strip()

    @property
    def unit_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for unit in self.units:
            counts[unit.unit_type] = counts.get(unit.unit_type, 0) + 1
        return counts

    def to_metadata(self, *, include_units: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source_ref": self.source_ref,
            "media_type": self.media_type,
            "converter_name": self.converter_name,
            "converter_version": self.converter_version,
            "content_hash": self.content_hash,
            "artifact_hash": self.artifact_hash,
            "unit_counts": self.unit_counts,
            "parse_quality": self.parse_quality.to_dict(),
            "warnings": list(self.warnings),
            "metadata": self.metadata,
        }
        if include_units:
            data["units"] = [unit.to_dict() for unit in self.units]
        return data

    def to_legacy(self) -> tuple[str, dict[str, Any]]:
        metadata = dict(self.metadata)
        metadata.update(
            {
                "media_type": self.media_type,
                "converter_name": self.converter_name,
                "converter_version": self.converter_version,
                "artifact_hash": self.artifact_hash,
                "unit_counts": self.unit_counts,
                "parse_quality": self.parse_quality.to_dict(),
                "intake_warnings": list(self.warnings),
            }
        )
        return self.text, metadata
