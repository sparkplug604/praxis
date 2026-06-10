"""Optional media probing and transcription helpers for Praxis intake."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .models import MissingDependencyError
from .media_adapters import (
    diarize_with_pyannote,
    scene_rows_from_scenedetect,
    visual_embed_with_openclip,
)
from .media_cache import (
    MEDIA_HELPER_VERSION,
    artifact_cache_root,
    cache_entries,
    cache_entry,
    cache_key,
    clear_cache,
    read_cached_transcript,
    sha256_bytes as _sha256_bytes,
    write_cached_transcript,
)
from .media_models import (
    DiarizationAdapter,
    DiarizationResult,
    KeyframeAdapter,
    KeyframeArtifact,
    KeyframeResult,
    MediaProbeResult,
    OcrAdapter,
    OcrResult,
    SceneArtifact,
    SttAdapter,
    TranscriptResult,
    VisualEmbeddingAdapter,
    VisualEmbeddingResult,
)
from .transcripts import parse_timestamp, segments_to_vtt


DEFAULT_STT_MODEL = "tiny"


def tool_path(name: str) -> str:
    return shutil.which(name) or ""


def tool_status(name: str) -> dict[str, str]:
    path = tool_path(name)
    if path:
        return {"tool": name, "status": "available", "path": path}
    return {"tool": name, "status": "missing_system_binary", "path": ""}


def _media_path(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[str, str | None]:
    """Return a filesystem path for media tools plus an optional temp path to clean up."""

    path = metadata.get("path")
    if path and Path(str(path)).exists():
        return str(path), None
    suffix = Path(source_ref).suffix or ".media"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(body)
        return handle.name, handle.name


def probe_media(source_ref: str, body: bytes, metadata: dict[str, Any], *, timeout: int = 15) -> MediaProbeResult:
    """Probe audio/video metadata with ffprobe when available."""

    if not tool_path("ffprobe"):
        return MediaProbeResult(warnings=["ffprobe_missing; media metadata limited"])
    path, temp_path = _media_path(source_ref, body, metadata)
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                path,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return MediaProbeResult(warnings=[f"ffprobe_error:{type(exc).__name__}"])
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink()
            except OSError:
                pass
    if result.returncode:
        message = result.stderr.strip().splitlines()[:1]
        detail = message[0] if message else f"exit_{result.returncode}"
        return MediaProbeResult(warnings=[f"ffprobe_failed:{detail[:120]}"])
    try:
        parsed = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return MediaProbeResult(warnings=["ffprobe_invalid_json"])
    return MediaProbeResult(metadata=_compact_probe(parsed))


def _compact_probe(parsed: dict[str, Any]) -> dict[str, Any]:
    fmt = parsed.get("format") or {}
    streams = parsed.get("streams") or []
    compact_streams: list[dict[str, Any]] = []
    for stream in streams:
        compact_streams.append(
            {
                "index": stream.get("index"),
                "codec_type": stream.get("codec_type"),
                "codec_name": stream.get("codec_name"),
                "duration": stream.get("duration"),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "r_frame_rate": stream.get("r_frame_rate"),
                "channels": stream.get("channels"),
                "sample_rate": stream.get("sample_rate"),
            }
        )
    return {
        "format_name": fmt.get("format_name"),
        "duration": fmt.get("duration"),
        "size": fmt.get("size"),
        "bit_rate": fmt.get("bit_rate"),
        "stream_count": len(compact_streams),
        "streams": compact_streams,
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def transcribe_media(
    source_ref: str,
    body: bytes,
    metadata: dict[str, Any],
    *,
    media_kind: str,
) -> TranscriptResult:
    """Transcribe media with a cached optional adapter."""

    model_name = str(metadata.get("_stt_model") or os.environ.get("PRAXIS_STT_MODEL") or DEFAULT_STT_MODEL)
    options = {
        "media_kind": media_kind,
        "model": model_name,
        "language": metadata.get("_stt_language") or os.environ.get("PRAXIS_STT_LANGUAGE") or "",
        "word_timestamps": _truthy(metadata.get("_word_timestamps") or os.environ.get("PRAXIS_STT_WORD_TIMESTAMPS")),
    }
    cached = read_cached_transcript(body, model_name, options)
    if cached:
        return cached

    adapter = metadata.get("_stt_adapter")
    if adapter is not None:
        text, adapter_metadata, adapter_warnings = adapter(source_ref, options)
        return write_cached_transcript(
            body,
            model_name,
            options,
            TranscriptResult(text=text, metadata={**adapter_metadata, "stt_adapter": "custom"}, warnings=list(adapter_warnings)),
        )

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - optional dependency
        raise MissingDependencyError("Speech-to-text requires faster-whisper. Install with: python3 -m pip install 'praxis-ktos[intake-stt]'") from exc

    path, temp_path = _media_path(source_ref, body, metadata)
    try:
        device = os.environ.get("PRAXIS_STT_DEVICE", "auto")
        compute_type = os.environ.get("PRAXIS_STT_COMPUTE_TYPE", "default")
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        segments, info = model.transcribe(
            path,
            language=options["language"] or None,
            vad_filter=True,
            word_timestamps=bool(options["word_timestamps"]),
        )
        segment_list = list(segments)
        text, word_records = segments_to_vtt(segment_list)
        transcript = TranscriptResult(
            text=text,
            metadata={
                "stt_adapter": "faster-whisper",
                "stt_model": model_name,
                "stt_language": getattr(info, "language", options["language"]),
                "stt_language_probability": getattr(info, "language_probability", None),
                "stt_segment_count": len(segment_list),
                "word_timestamps": word_records,
            },
            warnings=[] if text.strip() else ["speech_to_text_returned_no_text"],
        )
        return write_cached_transcript(body, model_name, options, transcript)
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink()
            except OSError:
                pass


def faster_whisper_status() -> dict[str, str]:
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return {
            "converter": "stt-faster-whisper",
            "status": "missing_optional_dependency",
            "notes": "Install with: python3 -m pip install 'praxis-ktos[intake-stt]'",
        }
    return {"converter": "stt-faster-whisper", "status": "available", "notes": "Optional local speech-to-text adapter is installed."}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _keyframe_options(metadata: dict[str, Any]) -> dict[str, Any]:
    timestamps = metadata.get("_keyframe_timestamps") or []
    if isinstance(timestamps, str):
        timestamps = [part.strip() for part in timestamps.split(",") if part.strip()]
    return {
        "strategy": str(metadata.get("_keyframe_strategy") or "interval"),
        "every_seconds": max(0.1, _safe_float(metadata.get("_keyframe_every_seconds"), 30.0)),
        "max_frames": max(1, int(_safe_float(metadata.get("_keyframe_max_frames"), 12))),
        "timestamps": [parse_timestamp(item) for item in timestamps],
        "scene_detector": str(metadata.get("_scene_detector") or "content"),
        "scene_threshold": _safe_float(metadata.get("_scene_threshold"), 27.0),
    }


def _keyframe_cache_dir(body: bytes, options: dict[str, Any]) -> Path:
    root = artifact_cache_root("keyframes") or (Path(tempfile.gettempdir()) / "praxis-intake" / "keyframes")
    key = cache_key(body, str(options.get("strategy") or "keyframes"), options)
    path = root / key
    path.mkdir(parents=True, exist_ok=True)
    return path


def _manifest_to_keyframes(path: Path) -> KeyframeResult | None:
    manifest = path / "manifest.json"
    if not manifest.exists():
        return None
    data = json.loads(manifest.read_text(encoding="utf-8"))
    keyframes: list[KeyframeArtifact] = []
    scenes: list[SceneArtifact] = []
    for item in data.get("scenes") or []:
        scenes.append(
            SceneArtifact(
                index=int(item.get("index") or len(scenes) + 1),
                start=_safe_float(item.get("start")),
                end=_safe_float(item.get("end")),
                detector=str(item.get("detector") or data.get("metadata", {}).get("scene_detector") or "unknown"),
                metadata=dict(item.get("metadata") or {}),
                warnings=list(item.get("warnings") or []),
            )
        )
    for item in data.get("keyframes") or []:
        frame_path = Path(str(item.get("path") or ""))
        if not frame_path.exists():
            return None
        keyframes.append(
            KeyframeArtifact(
                index=int(item.get("index") or len(keyframes) + 1),
                timestamp=_safe_float(item.get("timestamp")),
                path=str(frame_path),
                frame_hash=str(item.get("frame_hash") or ""),
                strategy=str(item.get("strategy") or data.get("strategy") or "unknown"),
                metadata=dict(item.get("metadata") or {}),
                warnings=list(item.get("warnings") or []),
            )
        )
    return KeyframeResult(
        keyframes=keyframes,
        scenes=scenes,
        metadata=dict(data.get("metadata") or {}),
        warnings=list(data.get("warnings") or []) + ["keyframe_cache_hit"],
    )


def _write_keyframe_manifest(path: Path, result: KeyframeResult) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "media_helper_version": MEDIA_HELPER_VERSION,
                "metadata": result.metadata,
                "warnings": result.warnings,
                "scenes": [
                    {
                        "index": scene.index,
                        "start": scene.start,
                        "end": scene.end,
                        "detector": scene.detector,
                        "metadata": scene.metadata,
                        "warnings": scene.warnings,
                    }
                    for scene in result.scenes
                ],
                "keyframes": [
                    {
                        "index": frame.index,
                        "timestamp": frame.timestamp,
                        "path": frame.path,
                        "frame_hash": frame.frame_hash,
                        "strategy": frame.strategy,
                        "metadata": frame.metadata,
                        "warnings": frame.warnings,
                    }
                    for frame in result.keyframes
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _bytes_to_keyframes(rows: list[dict[str, Any]], cache_dir: Path, strategy: str) -> list[KeyframeArtifact]:
    keyframes: list[KeyframeArtifact] = []
    for index, row in enumerate(rows, 1):
        body = bytes(row.get("bytes") or b"")
        extension = str(row.get("extension") or ".jpg")
        if not extension.startswith("."):
            extension = "." + extension
        if body:
            frame_hash = _sha256_bytes(body)
            path = cache_dir / f"frame-{index:05d}{extension}"
            path.write_bytes(body)
        else:
            source_path = Path(str(row.get("path") or ""))
            body = source_path.read_bytes()
            frame_hash = _sha256_bytes(body)
            path = source_path
        keyframes.append(
            KeyframeArtifact(
                index=index,
                timestamp=_safe_float(row.get("timestamp"), float(index - 1)),
                path=str(path),
                frame_hash=frame_hash,
                strategy=str(row.get("strategy") or strategy),
                metadata=dict(row.get("metadata") or {}),
                warnings=list(row.get("warnings") or []),
            )
        )
    return keyframes


def _scene_artifacts_from_rows(rows: list[dict[str, Any]], detector: str) -> list[SceneArtifact]:
    scenes: list[SceneArtifact] = []
    for index, row in enumerate(rows, 1):
        scenes.append(
            SceneArtifact(
                index=index,
                start=_safe_float(row.get("start")),
                end=_safe_float(row.get("end")),
                detector=str(row.get("detector") or detector),
                metadata=dict(row.get("metadata") or {}),
                warnings=list(row.get("warnings") or []),
            )
        )
    return scenes


def _extract_manual_frames(path: str, cache_dir: Path, timestamps: list[float], max_frames: int, strategy: str) -> tuple[list[KeyframeArtifact], list[str]]:
    frames: list[KeyframeArtifact] = []
    warnings: list[str] = []
    for index, timestamp in enumerate(timestamps[:max_frames], 1):
        frame_path = cache_dir / f"frame-{index:05d}.jpg"
        result = subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{timestamp:.3f}", "-i", path, "-frames:v", "1", str(frame_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode or not frame_path.exists():
            warnings.append(f"ffmpeg_keyframe_failed:{timestamp:.3f}")
            continue
        frame_body = frame_path.read_bytes()
        frames.append(
            KeyframeArtifact(
                index=index,
                timestamp=timestamp,
                path=str(frame_path),
                frame_hash=_sha256_bytes(frame_body),
                strategy=strategy,
            )
        )
    return frames, warnings


def extract_keyframes(source_ref: str, body: bytes, metadata: dict[str, Any]) -> KeyframeResult:
    """Extract a bounded set of keyframes from video."""

    options = _keyframe_options(metadata)
    cache_dir = _keyframe_cache_dir(body, options)
    cached = _manifest_to_keyframes(cache_dir)
    if cached:
        return cached

    adapter: KeyframeAdapter | None = metadata.get("_keyframe_adapter")
    if adapter is not None:
        rows, adapter_metadata, adapter_warnings = adapter(source_ref, options)
        scenes = _scene_artifacts_from_rows(list(adapter_metadata.get("scenes") or []), str(options["strategy"]))
        result = KeyframeResult(
            keyframes=_bytes_to_keyframes(rows[: int(options["max_frames"])], cache_dir, str(options["strategy"])),
            scenes=scenes,
            metadata={**adapter_metadata, "keyframe_adapter": "custom", "keyframe_cache_dir": str(cache_dir), **options},
            warnings=list(adapter_warnings),
        )
        _write_keyframe_manifest(cache_dir, result)
        return result

    if not tool_path("ffmpeg"):
        raise MissingDependencyError("Keyframe extraction requires ffmpeg. Install FFmpeg or provide a keyframe adapter.")

    strategy = str(options["strategy"])
    path, temp_path = _media_path(source_ref, body, metadata)
    try:
        output_pattern = cache_dir / "frame-%05d.jpg"
        if strategy == "manual":
            timestamps = options["timestamps"] or [0.0]
            frames, warnings = _extract_manual_frames(path, cache_dir, timestamps, int(options["max_frames"]), strategy)
            keyframe_result = KeyframeResult(keyframes=frames, metadata={"keyframe_cache_dir": str(cache_dir), **options}, warnings=warnings)
            _write_keyframe_manifest(cache_dir, keyframe_result)
            return keyframe_result
        if strategy == "scene":
            scene_rows, scene_metadata, scene_warnings = scene_rows_from_scenedetect(path, options)
            scenes = _scene_artifacts_from_rows(scene_rows, str(options["scene_detector"]))
            timestamps = [float(scene.metadata.get("midpoint") or (scene.start + max(0.0, scene.end - scene.start) / 2.0)) for scene in scenes]
            frames, frame_warnings = _extract_manual_frames(path, cache_dir, timestamps, int(options["max_frames"]), strategy)
            for frame, scene in zip(frames, scenes):
                frame.metadata = {**frame.metadata, "scene_index": scene.index, "scene_start": scene.start, "scene_end": scene.end}
            keyframe_result = KeyframeResult(
                keyframes=frames,
                scenes=scenes,
                metadata={"keyframe_cache_dir": str(cache_dir), **options, **scene_metadata},
                warnings=scene_warnings + frame_warnings,
            )
            _write_keyframe_manifest(cache_dir, keyframe_result)
            return keyframe_result
        if strategy != "interval":
            raise MissingDependencyError("Unsupported keyframe strategy. Use interval, manual, or scene.")
        every = float(options["every_seconds"])
        max_frames = int(options["max_frames"])
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-vf", f"fps=1/{every}", "-frames:v", str(max_frames), str(output_pattern)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            raise MissingDependencyError(f"ffmpeg keyframe extraction failed: {result.stderr.strip().splitlines()[:1]}")
        frames = []
        for index, frame_path in enumerate(sorted(cache_dir.glob("frame-*.jpg"))[:max_frames], 1):
            frames.append(
                KeyframeArtifact(
                    index=index,
                    timestamp=(index - 1) * every,
                    path=str(frame_path),
                    frame_hash=_sha256_bytes(frame_path.read_bytes()),
                    strategy=strategy,
                )
            )
        keyframe_result = KeyframeResult(keyframes=frames, metadata={"keyframe_cache_dir": str(cache_dir), **options}, warnings=[] if frames else ["ffmpeg_returned_no_keyframes"])
        _write_keyframe_manifest(cache_dir, keyframe_result)
        return keyframe_result
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink()
            except OSError:
                pass


def ocr_image_bytes(source_ref: str, image_bytes: bytes, metadata: dict[str, Any]) -> OcrResult:
    adapter: OcrAdapter | None = metadata.get("_ocr_adapter")
    if adapter is not None:
        text, adapter_metadata, adapter_warnings = adapter(source_ref, image_bytes, metadata)
        return OcrResult(text=text, metadata={**adapter_metadata, "ocr_adapter": "custom"}, warnings=list(adapter_warnings))
    try:
        from PIL import Image
        import pytesseract
    except Exception as exc:  # pragma: no cover - optional dependency
        raise MissingDependencyError("OCR requires Pillow and pytesseract. Install with: python3 -m pip install 'praxis-ktos[intake-ocr]'") from exc
    from io import BytesIO

    image = Image.open(BytesIO(image_bytes))
    text = pytesseract.image_to_string(image)
    return OcrResult(
        text=text,
        metadata={"ocr_adapter": "pytesseract", "image_width": image.width, "image_height": image.height},
        warnings=[] if text.strip() else ["ocr_returned_no_text"],
    )


def diarize_media(source_ref: str, body: bytes, metadata: dict[str, Any]) -> DiarizationResult:
    adapter: DiarizationAdapter | None = metadata.get("_diarization_adapter")
    if adapter is not None:
        turns, adapter_metadata, adapter_warnings = adapter(source_ref, metadata)
        return DiarizationResult(turns=turns, metadata={**adapter_metadata, "diarization_adapter": "custom"}, warnings=list(adapter_warnings))
    path, temp_path = _media_path(source_ref, body, metadata)
    try:
        return diarize_with_pyannote(path, metadata)
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink()
            except OSError:
                pass


def visual_embed_image(source_ref: str, image_bytes: bytes, metadata: dict[str, Any]) -> VisualEmbeddingResult:
    adapter: VisualEmbeddingAdapter | None = metadata.get("_visual_embedding_adapter")
    if adapter is not None:
        vector, adapter_metadata, adapter_warnings = adapter(source_ref, image_bytes, metadata)
        return VisualEmbeddingResult(vector=vector, metadata={**adapter_metadata, "visual_embedding_adapter": "custom"}, warnings=list(adapter_warnings))
    return visual_embed_with_openclip(image_bytes, metadata)


def optional_package_status(package: str, *, converter: str, notes: str) -> dict[str, str]:
    try:
        __import__(package)
    except Exception:
        return {"converter": converter, "status": "missing_optional_dependency", "notes": notes}
    return {"converter": converter, "status": "available", "notes": "Optional adapter package is installed."}
