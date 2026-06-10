"""Transcript parsing and timestamp alignment helpers for Praxis intake."""

from __future__ import annotations

import re
from typing import Any

from .models import ExtractedUnit
from .units import make_unit


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    if ":" not in text:
        return safe_float(text)
    parts = text.replace(",", ".").split(":")
    seconds = safe_float(parts[-1])
    minutes = int(parts[-2]) if len(parts) >= 2 and parts[-2].isdigit() else 0
    hours = int(parts[-3]) if len(parts) >= 3 and parts[-3].isdigit() else 0
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def segment_words(segment: Any) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for word in getattr(segment, "words", []) or []:
        text = str(getattr(word, "word", "") or "").strip()
        if not text:
            continue
        words.append(
            {
                "word": text,
                "start": float(getattr(word, "start", 0.0) or 0.0),
                "end": float(getattr(word, "end", 0.0) or 0.0),
                "probability": getattr(word, "probability", None),
            }
        )
    return words


def segments_to_vtt(segments: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    lines = ["WEBVTT", ""]
    word_records: list[dict[str, Any]] = []
    for index, segment in enumerate(segments, 1):
        start = float(getattr(segment, "start", 0.0) or 0.0)
        end = float(getattr(segment, "end", start) or start)
        text = str(getattr(segment, "text", "") or "").strip()
        if not text:
            continue
        lines.extend([str(index), f"{format_timestamp(start)} --> {format_timestamp(end)}", text, ""])
        for word in segment_words(segment):
            word_records.append({"segment_index": index, **word})
    return "\n".join(lines).strip() + "\n", word_records


def parse_timed_transcript(source_ref: str, transcript: str, *, unit_type: str = "transcript_segment") -> list[ExtractedUnit]:
    """Parse SRT/VTT-ish transcript text into timestamped evidence units."""

    cleaned = transcript.strip()
    if not cleaned:
        return []
    blocks = re.split(r"\n\s*\n", cleaned)
    units: list[ExtractedUnit] = []
    time_pattern = re.compile(
        r"(?P<start>\d{1,2}:\d{2}:\d{2}(?:[,.]\d{1,3})?)\s*-->\s*(?P<end>\d{1,2}:\d{2}:\d{2}(?:[,.]\d{1,3})?)"
    )
    for index, block in enumerate(blocks, 1):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if len(lines) == 1 and lines[0].upper().startswith("WEBVTT"):
            continue
        match = None
        time_line_index = -1
        for line_index, line in enumerate(lines):
            match = time_pattern.search(line)
            if match:
                time_line_index = line_index
                break
        if match:
            text_lines = lines[time_line_index + 1 :]
            if not text_lines:
                continue
            start = match.group("start").replace(",", ".")
            end = match.group("end").replace(",", ".")
            text = " ".join(text_lines)
            units.append(
                make_unit(
                    source_ref,
                    unit_type,
                    text,
                    index=index,
                    markdown=f"## {start} --> {end}\n\n{text}",
                    location={"start": start, "end": end},
                    confidence="medium",
                )
            )
        else:
            text = " ".join(lines)
            units.append(make_unit(source_ref, unit_type, text, index=index, location={"segment": index}, confidence="medium"))
    if not units:
        units.append(make_unit(source_ref, "transcript", cleaned, location={"source": source_ref}, confidence="medium"))
    return units


def words_for_segment(words: list[dict[str, Any]], location: dict[str, Any]) -> list[dict[str, Any]]:
    start = parse_timestamp(location.get("start"))
    end = parse_timestamp(location.get("end"))
    if end <= start:
        return []
    return [
        word
        for word in words
        if float(word.get("start") or 0.0) >= start and float(word.get("end") or 0.0) <= end
    ]


def speaker_for_segment(turns: list[dict[str, Any]], location: dict[str, Any]) -> str:
    start = parse_timestamp(location.get("start"))
    end = parse_timestamp(location.get("end"))
    best_speaker = ""
    best_overlap = 0.0
    for turn in turns:
        turn_start = float(turn.get("start") or 0.0)
        turn_end = float(turn.get("end") or 0.0)
        overlap = max(0.0, min(end, turn_end) - max(start, turn_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = str(turn.get("speaker_id") or turn.get("speaker") or "")
    return best_speaker
