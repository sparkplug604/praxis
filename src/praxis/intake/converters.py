"""Built-in source converters for Praxis intake."""

from __future__ import annotations

import html.parser
import io
import re
from pathlib import Path
from typing import Any

from .media import (
    diarize_media,
    extract_keyframes,
    ocr_image_bytes,
    probe_media,
    transcribe_media,
    visual_embed_image,
)
from .models import ExtractedUnit, MissingDependencyError
from .office import convert_docx, convert_pptx, convert_xlsx
from .structured import convert_csv, convert_json
from .text import decode_text
from .transcripts import parse_timed_transcript, speaker_for_segment, words_for_segment
from .units import make_unit, media_evidence_metadata, sha256_bytes, sha256_text


CONVERTER_VERSION = "1"


def convert_text(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    text = decode_text(body)
    return [make_unit(source_ref, "document", text, location={"source": source_ref})], metadata, []


def convert_markdown(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    text = decode_text(body)
    return [make_unit(source_ref, "markdown_document", text, location={"source": source_ref})], metadata, []


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

    @staticmethod
    def text(parts: list[str]) -> str:
        raw = " ".join(parts)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s+", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def html_to_text(raw: str) -> str:
    parser = _TableExtractor()
    parser.feed(raw)
    parser.close()
    return "\n\n".join(unit.text for unit in parser.units(""))


def convert_html(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    parser = _TableExtractor()
    parser.feed(decode_text(body))
    parser.close()
    return parser.units(source_ref), metadata, parser.warnings


class _TableExtractor(_HTMLTextExtractor):
    """Replace unambiguous rows in place; retain legacy text for other layouts."""

    def __init__(self):
        super().__init__()
        self.depth = self.table_no = 0
        self.heading = ""
        self.heading_start = None
        self.replacements = []
        self.warnings = []

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if self._skip:
            return
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.table_no += 1
                self.pending = []
                self.invalid = False
                self.columns = []
                self.group = ""
                self.caption = ""
                self.caption_start = None
                self.row_start = self.cell = None
                self.row_no = 0
            else:
                self.invalid = True
        if not self.depth and tag in {"h1", "h2", "h3", "h4"}:
            self.heading_start = len(self.parts)
        if self.depth != 1 or self.invalid:
            return
        if tag == "caption":
            self.caption_start = len(self.parts)
        elif tag == "tr":
            self.invalid = self.row_start is not None
            self.row_start = len(self.parts)
            self.row_no += 1
            self.cells = []
        elif tag in {"td", "th"}:
            attrs = dict(attrs)
            self.invalid = (self.row_start is None or self.cell is not None
                            or attrs.get("rowspan", "1") != "1" or "headers" in attrs)
            self.cell = (tag, attrs.get("colspan", "1"), len(self.parts))

    def handle_endtag(self, tag):
        if not self._skip:
            if self.depth == 1 and not self.invalid:
                if tag in {"td", "th"}:
                    if not self.cell or self.cell[0] != tag:
                        self.invalid = True
                    else:
                        kind, span, start = self.cell
                        value = " ".join("".join(self.parts[start:]).split())
                        self.cells.append((kind, span, value))
                        self.cell = None
                elif tag == "tr":
                    self.finish_row()
                elif tag == "caption" and self.caption_start is not None:
                    self.caption = " ".join("".join(self.parts[self.caption_start:]).split())
                    self.caption_start = None
            if tag == "table" and self.depth:
                self.depth -= 1
                if not self.depth:
                    if self.invalid or self.row_start is not None or not self.pending:
                        self.warnings.append(f"html_table_{self.table_no}: preserved as unstructured text")
                    else:
                        self.replacements.extend(self.pending)
            elif not self.depth and tag in {"h1", "h2", "h3", "h4"} and self.heading_start is not None:
                self.heading = " ".join("".join(self.parts[self.heading_start:]).split())
                self.heading_start = None
        super().handle_endtag(tag)

    def finish_row(self):
        start, self.row_start = self.row_start, None
        if start is None or self.cell is not None or not self.cells:
            self.invalid = True
            return
        kinds, spans, values = zip(*self.cells)
        if len(values) == 1 and kinds == ("th",):
            self.group, self.columns = values[0], []
            if self.row_no == 1 and not self.caption:
                self.caption = self.group
            return
        if len(values) == 1 and not self.columns and kinds == ("td",):
            # A full-width illustration/description has no label/value binding.
            return
        if any(s != "1" for s in spans):
            self.invalid = True
            return
        if all(k == "th" for k in kinds):
            # Do not silently discard a level of multi-tier column headings.
            if self.columns or not all(values) or len(set(values)) != len(values):
                self.invalid = True
            self.columns = values
            return
        if self.columns and len(self.columns) == len(values):
            pairs = list(zip(self.columns, values))
        elif not self.columns and kinds == ("th", "td") and values[0]:
            pairs = [(values[0], values[1])]
        else:
            self.invalid = True
            return
        context = list(dict.fromkeys(s for s in (self.heading, self.caption, self.group) if s))
        if sum(map(len, context)) + sum(len(k) for k, _ in pairs) > 1024:
            self.invalid = True
            return
        text = "; ".join(context + [f"{k}: {v}" for k, v in pairs])
        self.pending.append((start, len(self.parts), self.table_no, self.row_no, text, pairs))

    def units(self, source):
        result = []

        def prose(parts):
            text = self.text(parts)
            if text:
                result.append(make_unit(source, "html_document", text, index=len(result) + 1,
                                        location={"source": source}))

        cursor = 0
        for start, end, table, row, text, pairs in self.replacements:
            prose(self.parts[cursor:start])
            result.append(make_unit(source, "table_row", text, index=len(result),
                                    location={"source": source, "table": table, "row": row},
                                    structured_data={"fields": dict(pairs)}))
            cursor = end
        prose(self.parts[cursor:])
        if self.depth:
            self.warnings.append("unclosed_html_table: preserved as unstructured text")
        return result


def convert_pdf(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - depends on optional dependency
        raise MissingDependencyError("PDF intake requires pypdf. Install with: python3 -m pip install 'praxis-ktos[intake-basic]'") from exc

    reader = PdfReader(io.BytesIO(body))
    warnings: list[str] = []
    units: list[ExtractedUnit] = []
    for index, page in enumerate(reader.pages, 1):
        extracted = page.extract_text() or ""
        if extracted.strip():
            units.append(make_unit(source_ref, "page", extracted, index=index, markdown=f"## Page {index}\n\n{extracted.strip()}", location={"page": index}))
        else:
            warnings.append(f"pdf_page_{index}_empty_or_unreadable")
    metadata = {**metadata, "pdf_pages": len(reader.pages)}
    if not units:
        warnings.append("pdf_has_no_extractable_text; scanned PDF may need OCR")
    return units, metadata, warnings


def convert_transcript_sidecar(
    source_ref: str,
    transcript_text: str,
    metadata: dict[str, Any],
    *,
    media_kind: str,
    sidecar_path: str,
) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    units = parse_timed_transcript(source_ref, transcript_text, unit_type=f"{media_kind}_transcript_segment")
    if not units:
        return [], metadata, ["transcript_sidecar_empty"]
    return (
        units,
        {
            **metadata,
            "sidecar_path": sidecar_path,
            "sidecar_type": "transcript",
            "media_kind": media_kind,
        },
        [f"{media_kind}_transcript_sidecar_used"],
    )


def convert_ocr_sidecar(
    source_ref: str,
    ocr_text: str,
    metadata: dict[str, Any],
    *,
    sidecar_path: str,
) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    unit = make_unit(
        source_ref,
        "image_text",
        ocr_text,
        location={"source": source_ref, "sidecar_path": sidecar_path},
        confidence="medium",
        warnings=["image_ocr_sidecar_used"],
    )
    return [unit], {**metadata, "sidecar_path": sidecar_path, "sidecar_type": "ocr"}, ["image_ocr_sidecar_used"]


def convert_image(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - optional dependency
        raise MissingDependencyError("Image intake requires Pillow for metadata and pytesseract for OCR. Install with: python3 -m pip install 'praxis-ktos[intake-ocr]'") from exc

    image = Image.open(io.BytesIO(body))
    image_metadata = {**metadata, "image_width": image.width, "image_height": image.height, "image_mode": image.mode}
    try:
        import pytesseract
    except Exception as exc:  # pragma: no cover - optional dependency
        raise MissingDependencyError("Image OCR requires pytesseract. Install OCR dependencies before ingesting images as searchable text.") from exc
    text = pytesseract.image_to_string(image)
    warnings = [] if text.strip() else ["ocr_returned_no_text"]
    return [make_unit(source_ref, "image_text", text, location={"source": source_ref}, confidence="low", warnings=warnings)], image_metadata, warnings


def _public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if not key.startswith("_")}


def _media_asset_unit(
    source_ref: str,
    *,
    media_kind: str,
    metadata: dict[str, Any],
    warnings: list[str],
) -> ExtractedUnit:
    media = metadata.get("media_probe") or {}
    lines = [
        f"Media source: {source_ref}",
        f"Media kind: {media_kind}",
        f"Media type: {metadata.get('media_type', '')}",
    ]
    if media.get("duration"):
        lines.append(f"Duration: {media['duration']} seconds")
    if media.get("stream_count") is not None:
        lines.append(f"Streams: {media['stream_count']}")
    if warnings:
        lines.append("Warnings: " + "; ".join(warnings))
    text = "\n".join(line for line in lines if line.strip())
    return make_unit(
        source_ref,
        f"{media_kind}_asset",
        text,
        location={"source": source_ref},
        structured_data=media_evidence_metadata(
            lifecycle="raw",
            confidence_reason="metadata-only media asset; no searchable transcript was extracted",
            extra={"media_probe": media},
        ),
        confidence="low",
        warnings=list(warnings),
    )


def _keyframe_units(source_ref: str, keyframe_result, metadata: dict[str, Any]) -> list[ExtractedUnit]:
    units: list[ExtractedUnit] = []
    for scene in keyframe_result.scenes:
        text = f"Video scene {scene.index} from {scene.start:.3f}s to {scene.end:.3f}s in {source_ref}"
        units.append(
            make_unit(
                source_ref,
                "video_scene",
                text,
                index=scene.index,
                markdown=f"## Scene {scene.index} ({scene.start:.3f}s → {scene.end:.3f}s)\n\n{text}",
                structured_data=media_evidence_metadata(
                    adapter_name=str(keyframe_result.metadata.get("scene_adapter") or "scenedetect"),
                    model_name=str(keyframe_result.metadata.get("scene_detector") or scene.detector),
                    confidence_reason="scene boundary from optional scene-detection adapter",
                    extra={
                        "start": scene.start,
                        "end": scene.end,
                        "detector": scene.detector,
                        "metadata": scene.metadata,
                    },
                ),
                location={"start": scene.start, "end": scene.end},
                confidence="medium",
                warnings=list(scene.warnings),
            )
        )
    for index, frame in enumerate(keyframe_result.keyframes, 1):
        text = f"Video keyframe {index} at {frame.timestamp:.3f}s from {source_ref}"
        units.append(
            make_unit(
                source_ref,
                "video_keyframe",
                text,
                index=index,
                markdown=f"## Keyframe {index} ({frame.timestamp:.3f}s)\n\n{text}",
                structured_data=media_evidence_metadata(
                    adapter_name=str(keyframe_result.metadata.get("keyframe_adapter") or "ffmpeg"),
                    model_name=frame.strategy,
                    confidence_reason="selected frame from video; it is visual evidence, not full video understanding",
                    extra={
                        "timestamp": frame.timestamp,
                        "frame_path": frame.path,
                        "frame_hash": frame.frame_hash,
                        "strategy": frame.strategy,
                        "metadata": frame.metadata,
                    },
                ),
                location={"timestamp": frame.timestamp, "frame_path": frame.path},
                confidence="medium",
                warnings=list(frame.warnings),
            )
        )
    return units


def _ocr_keyframe_units(source_ref: str, keyframe_units: list[ExtractedUnit], metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], list[str]]:
    units: list[ExtractedUnit] = []
    warnings: list[str] = []
    for index, frame_unit in enumerate(keyframe_units, 1):
        frame_path = frame_unit.structured_data.get("frame_path")
        if not frame_path:
            continue
        try:
            image_bytes = Path(str(frame_path)).read_bytes()
            ocr = ocr_image_bytes(source_ref, image_bytes, {**metadata, "keyframe": frame_unit.structured_data})
        except MissingDependencyError as exc:
            warnings.append(f"keyframe_ocr_unavailable:{exc}")
            continue
        except Exception as exc:  # pragma: no cover - optional adapter boundary
            warnings.append(f"keyframe_ocr_failed:{type(exc).__name__}")
            continue
        warnings.extend(ocr.warnings)
        text = ocr.text.strip()
        if not text:
            continue
        timestamp = frame_unit.structured_data.get("timestamp")
        units.append(
            make_unit(
                source_ref,
                "video_frame_text",
                text,
                index=index,
                markdown=f"## OCR for keyframe {index} ({timestamp}s)\n\n{text}",
                structured_data=media_evidence_metadata(
                    adapter_name=str(ocr.metadata.get("ocr_adapter") or "ocr"),
                    model_name=str(ocr.metadata.get("ocr_engine") or ocr.metadata.get("ocr_adapter") or ""),
                    confidence_reason="OCR over a selected video frame; recognition errors are possible",
                    extra={"ocr": ocr.metadata, "keyframe": frame_unit.structured_data},
                ),
                location={"timestamp": timestamp, "frame_path": frame_path},
                parent_unit_id=frame_unit.unit_id,
                confidence="low",
                warnings=ocr.warnings,
            )
        )
    return units, warnings


def _visual_embedding_units(source_ref: str, keyframe_units: list[ExtractedUnit], metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], list[str]]:
    units: list[ExtractedUnit] = []
    warnings: list[str] = []
    for index, frame_unit in enumerate(keyframe_units, 1):
        frame_path = frame_unit.structured_data.get("frame_path")
        if not frame_path:
            continue
        try:
            image_bytes = Path(str(frame_path)).read_bytes()
            embedding = visual_embed_image(source_ref, image_bytes, {**metadata, "keyframe": frame_unit.structured_data})
        except MissingDependencyError as exc:
            warnings.append(f"visual_embedding_unavailable:{exc}")
            continue
        except Exception as exc:  # pragma: no cover - optional adapter boundary
            warnings.append(f"visual_embedding_failed:{type(exc).__name__}")
            continue
        warnings.extend(embedding.warnings)
        timestamp = frame_unit.structured_data.get("timestamp")
        text = f"Visual embedding for keyframe {index} at {timestamp}s from {source_ref}"
        units.append(
            make_unit(
                source_ref,
                "visual_embedding",
                text,
                index=index,
                structured_data=media_evidence_metadata(
                    adapter_name=str(embedding.metadata.get("visual_embedding_adapter") or "visual"),
                    model_name=str(embedding.metadata.get("visual_model") or embedding.metadata.get("embedding_model") or ""),
                    confidence_reason="visual retrieval signal; keep separate from text evidence",
                    extra={"vector": embedding.vector, "embedding": embedding.metadata, "keyframe": frame_unit.structured_data},
                ),
                location={"timestamp": timestamp, "frame_path": frame_path},
                parent_unit_id=frame_unit.unit_id,
                confidence="medium",
                warnings=embedding.warnings,
            )
        )
    return units, warnings


def _speaker_turn_units(source_ref: str, turns: list[dict[str, Any]]) -> list[ExtractedUnit]:
    units: list[ExtractedUnit] = []
    for index, turn in enumerate(turns, 1):
        speaker_id = str(turn.get("speaker_id") or turn.get("speaker") or f"speaker_{index}")
        start = float(turn.get("start") or 0.0)
        end = float(turn.get("end") or start)
        text = f"{speaker_id} speaks from {start:.3f}s to {end:.3f}s"
        units.append(
            make_unit(
                source_ref,
                "speaker_turn",
                text,
                index=index,
                structured_data=media_evidence_metadata(
                    adapter_name=str(turn.get("diarization_adapter") or "diarization"),
                    model_name=str(turn.get("diarization_model") or ""),
                    confidence_reason="speaker label is provisional turn-taking evidence, not verified identity",
                    extra={"speaker_turn": turn},
                ),
                location={"start": start, "end": end},
                confidence=str(turn.get("confidence") or "low"),
            )
        )
    return units


def _convert_media(
    source_ref: str,
    body: bytes,
    metadata: dict[str, Any],
    *,
    media_kind: str,
) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    public_metadata = _public_metadata(metadata)
    warnings: list[str] = []
    probe = probe_media(source_ref, body, metadata)
    warnings.extend(probe.warnings)
    converter_metadata: dict[str, Any] = {
        **public_metadata,
        "media_kind": media_kind,
        "media_probe": probe.metadata,
    }
    try:
        transcript = transcribe_media(source_ref, body, metadata, media_kind=media_kind)
    except MissingDependencyError as exc:
        warnings.append(f"speech_to_text_unavailable:{exc}")
    except Exception as exc:  # pragma: no cover - defensive boundary around optional adapters
        warnings.append(f"speech_to_text_failed:{type(exc).__name__}")
    else:
        warnings.extend(transcript.warnings)
        converter_metadata.update(transcript.metadata)
        units = parse_timed_transcript(source_ref, transcript.text, unit_type=f"{media_kind}_transcript_segment")
        if units:
            words = list(transcript.metadata.get("word_timestamps") or [])
            speaker_turns: list[dict[str, Any]] = []
            if metadata.get("_diarize"):
                try:
                    diarization = diarize_media(source_ref, body, metadata)
                    warnings.extend(diarization.warnings)
                    converter_metadata.update(diarization.metadata)
                    speaker_turns = diarization.turns
                    units.extend(_speaker_turn_units(source_ref, speaker_turns))
                except MissingDependencyError as exc:
                    warnings.append(f"diarization_unavailable:{exc}")
                except Exception as exc:  # pragma: no cover - optional adapter boundary
                    warnings.append(f"diarization_failed:{type(exc).__name__}")
            for unit in units:
                if "transcript_segment" in unit.unit_type:
                    unit.confidence = "medium"
                    segment_words = words_for_segment(words, unit.location)
                    speaker_id = speaker_for_segment(speaker_turns, unit.location)
                    unit.structured_data = {
                        **unit.structured_data,
                        **media_evidence_metadata(
                            adapter_name=str(transcript.metadata.get("stt_adapter") or "transcript"),
                            model_name=str(transcript.metadata.get("stt_model") or ""),
                            confidence_reason="timestamped transcript segment from sidecar or speech-to-text adapter",
                        ),
                        "transcript_metadata": transcript.metadata,
                        "word_timestamps": segment_words,
                        "speaker_id": speaker_id,
                    }
            if media_kind == "video" and metadata.get("_extract_keyframes"):
                keyframe_units, keyframe_warnings, keyframe_metadata = _media_keyframe_units(source_ref, body, metadata)
                warnings.extend(keyframe_warnings)
                converter_metadata.update(keyframe_metadata)
                units.extend(keyframe_units)
            return units, {**converter_metadata, "_converter_name": f"{media_kind}-stt"}, warnings
        warnings.append("speech_to_text_returned_no_units")
    if media_kind == "video" and metadata.get("_extract_keyframes"):
        keyframe_units, keyframe_warnings, keyframe_metadata = _media_keyframe_units(source_ref, body, metadata)
        warnings.extend(keyframe_warnings)
        converter_metadata.update(keyframe_metadata)
        if keyframe_units:
            return keyframe_units, {**converter_metadata, "_converter_name": "video-keyframes"}, warnings
    warnings.append("no_transcript_extracted; media archived as low-confidence metadata only")
    unit = _media_asset_unit(source_ref, media_kind=media_kind, metadata=converter_metadata, warnings=warnings)
    return [unit], {**converter_metadata, "_converter_name": f"{media_kind}-media"}, warnings


def _media_keyframe_units(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], list[str], dict[str, Any]]:
    try:
        keyframes = extract_keyframes(source_ref, body, metadata)
    except MissingDependencyError as exc:
        return [], [f"keyframe_extraction_unavailable:{exc}"], {}
    except Exception as exc:  # pragma: no cover - optional adapter boundary
        return [], [f"keyframe_extraction_failed:{type(exc).__name__}"], {}
    warnings = list(keyframes.warnings)
    units = _keyframe_units(source_ref, keyframes, metadata)
    if metadata.get("_ocr_keyframes"):
        ocr_units, ocr_warnings = _ocr_keyframe_units(source_ref, units, metadata)
        units.extend(ocr_units)
        warnings.extend(ocr_warnings)
    if metadata.get("_visual_embeddings"):
        visual_units, visual_warnings = _visual_embedding_units(source_ref, units, metadata)
        units.extend(visual_units)
        warnings.extend(visual_warnings)
    return units, warnings, {"keyframes": keyframes.metadata, "keyframe_count": len(keyframes.keyframes)}


def convert_audio(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    return _convert_media(source_ref, body, metadata, media_kind="audio")


def convert_video(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    return _convert_media(source_ref, body, metadata, media_kind="video")
