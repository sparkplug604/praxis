"""Media intake data contracts and adapter type aliases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


SttAdapter = Callable[[str, dict[str, Any]], tuple[str, dict[str, Any], list[str]]]
KeyframeAdapter = Callable[[str, dict[str, Any]], tuple[list[dict[str, Any]], dict[str, Any], list[str]]]
OcrAdapter = Callable[[str, bytes, dict[str, Any]], tuple[str, dict[str, Any], list[str]]]
DiarizationAdapter = Callable[[str, dict[str, Any]], tuple[list[dict[str, Any]], dict[str, Any], list[str]]]
VisualEmbeddingAdapter = Callable[[str, bytes, dict[str, Any]], tuple[list[float], dict[str, Any], list[str]]]


@dataclass
class MediaProbeResult:
    """Metadata from ffprobe or a safe fallback when probing is unavailable."""

    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TranscriptResult:
    """Timestamped transcript artifact returned by a speech-to-text adapter."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class KeyframeArtifact:
    """A selected video frame stored as a source-linked artifact."""

    index: int
    timestamp: float
    path: str
    frame_hash: str
    strategy: str
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SceneArtifact:
    """A detected video scene used to choose source-linked keyframes."""

    index: int
    start: float
    end: float
    detector: str
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class KeyframeResult:
    """Selected keyframes plus extraction metadata."""

    keyframes: list[KeyframeArtifact] = field(default_factory=list)
    scenes: list[SceneArtifact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class OcrResult:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DiarizationResult:
    turns: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class VisualEmbeddingResult:
    vector: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
