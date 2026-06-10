"""Optional heavy media adapters for Praxis intake.

These functions are imported lazily by the media orchestration layer and should
not be required for normal Praxis startup.
"""

from __future__ import annotations

import os
from typing import Any

from .media_models import DiarizationResult, VisualEmbeddingResult
from .models import MissingDependencyError


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def seconds_from_timecode(value: Any) -> float:
    if hasattr(value, "get_seconds"):
        return _safe_float(value.get_seconds())
    return _safe_float(value)


def scene_rows_from_scenedetect(path: str, options: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    try:
        from scenedetect import AdaptiveDetector, ContentDetector, ThresholdDetector, detect
    except Exception as exc:  # pragma: no cover - optional dependency
        raise MissingDependencyError("Scene-aware keyframes require scenedetect. Install with: python3 -m pip install 'praxis-ktos[intake-scenes]'") from exc

    detector_name = str(options.get("scene_detector") or "content").lower()
    threshold = float(options.get("scene_threshold") or 27.0)
    if detector_name == "adaptive":
        detector = AdaptiveDetector(adaptive_threshold=threshold)
    elif detector_name == "threshold":
        detector = ThresholdDetector(threshold=threshold)
    else:
        detector_name = "content"
        detector = ContentDetector(threshold=threshold)
    scenes = detect(path, detector)
    rows: list[dict[str, Any]] = []
    for index, (start_time, end_time) in enumerate(scenes[: int(options["max_frames"])], 1):
        start = seconds_from_timecode(start_time)
        end = seconds_from_timecode(end_time)
        rows.append(
            {
                "index": index,
                "start": start,
                "end": end,
                "detector": detector_name,
                "metadata": {"midpoint": start + max(0.0, end - start) / 2.0},
            }
        )
    warnings = [] if rows else ["scenedetect_returned_no_scenes"]
    return rows, {"scene_adapter": "scenedetect", "scene_detector": detector_name, "scene_threshold": threshold}, warnings


def diarize_with_pyannote(path: str, metadata: dict[str, Any]) -> DiarizationResult:
    try:
        from pyannote.audio import Pipeline
    except Exception as exc:  # pragma: no cover - optional dependency
        raise MissingDependencyError("Speaker diarization requires pyannote.audio. Install with: python3 -m pip install 'praxis-ktos[intake-diarization]'") from exc

    token = os.environ.get("PYANNOTE_AUTH_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
    if not token:
        raise MissingDependencyError("Speaker diarization requires PYANNOTE_AUTH_TOKEN, HUGGINGFACE_TOKEN, or HF_TOKEN.")
    model_name = str(metadata.get("_diarization_model") or os.environ.get("PRAXIS_PYANNOTE_MODEL") or "pyannote/speaker-diarization-community-1")
    pipeline = Pipeline.from_pretrained(model_name, token=token)
    kwargs: dict[str, Any] = {}
    for source_key, target_key in (
        ("_num_speakers", "num_speakers"),
        ("_min_speakers", "min_speakers"),
        ("_max_speakers", "max_speakers"),
    ):
        if metadata.get(source_key) is not None:
            kwargs[target_key] = int(metadata[source_key])
    diarization = pipeline(path, **kwargs)
    turns: list[dict[str, Any]] = []
    for segment, _, speaker in diarization.itertracks(yield_label=True):
        turns.append(
            {
                "speaker_id": str(speaker),
                "start": float(segment.start),
                "end": float(segment.end),
                "confidence": "medium",
            }
        )
    warnings = [] if turns else ["pyannote_returned_no_speaker_turns"]
    return DiarizationResult(
        turns=turns,
        metadata={
            "diarization_adapter": "pyannote",
            "diarization_model": model_name,
            "speaker_turn_count": len(turns),
            **kwargs,
        },
        warnings=warnings,
    )


def visual_embed_with_openclip(image_bytes: bytes, metadata: dict[str, Any]) -> VisualEmbeddingResult:
    try:
        import torch
        import open_clip
        from PIL import Image
    except Exception as exc:  # pragma: no cover - optional dependency
        raise MissingDependencyError("Visual embeddings require open_clip_torch, torch, and Pillow. Install with: python3 -m pip install 'praxis-ktos[intake-visual]'") from exc
    from io import BytesIO

    model_name = str(metadata.get("_visual_model") or os.environ.get("PRAXIS_OPENCLIP_MODEL") or "ViT-B-32")
    pretrained = str(metadata.get("_visual_pretrained") or os.environ.get("PRAXIS_OPENCLIP_PRETRAINED") or "laion2b_s34b_b79k")
    device = str(metadata.get("_visual_device") or os.environ.get("PRAXIS_OPENCLIP_DEVICE") or "cpu")
    model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained, device=device)
    model.eval()
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    with torch.no_grad():
        tensor = preprocess(image).unsqueeze(0).to(device)
        vector_tensor = model.encode_image(tensor)
        vector_tensor = vector_tensor / vector_tensor.norm(dim=-1, keepdim=True)
    vector = [float(value) for value in vector_tensor.squeeze(0).detach().cpu().tolist()]
    return VisualEmbeddingResult(
        vector=vector,
        metadata={
            "visual_embedding_adapter": "openclip",
            "visual_model": model_name,
            "visual_pretrained": pretrained,
            "visual_device": device,
            "dimensions": len(vector),
        },
        warnings=[],
    )
