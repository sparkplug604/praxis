#!/usr/bin/env python3
"""Inspect and convert sources before Praxis stores them as evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from praxis.intake import converter_doctor, extract_source, inspect_source
from praxis.intake.media_cache import cache_entries, cache_entry, clear_cache


def media_metadata_from_args(args) -> dict:
    metadata = {}
    if getattr(args, "extract_keyframes", False):
        metadata["_extract_keyframes"] = True
    if getattr(args, "ocr_keyframes", False):
        metadata["_extract_keyframes"] = True
        metadata["_ocr_keyframes"] = True
    if getattr(args, "visual_embeddings", False):
        metadata["_extract_keyframes"] = True
        metadata["_visual_embeddings"] = True
    if getattr(args, "word_timestamps", False):
        metadata["_word_timestamps"] = True
    if getattr(args, "diarize", False):
        metadata["_diarize"] = True
    if getattr(args, "keyframe_strategy", None):
        metadata["_keyframe_strategy"] = args.keyframe_strategy
    if getattr(args, "keyframe_every_seconds", None) is not None:
        metadata["_keyframe_every_seconds"] = args.keyframe_every_seconds
    if getattr(args, "keyframe_max_frames", None) is not None:
        metadata["_keyframe_max_frames"] = args.keyframe_max_frames
    if getattr(args, "keyframe_timestamps", None):
        metadata["_keyframe_timestamps"] = args.keyframe_timestamps
    if getattr(args, "scene_detector", None):
        metadata["_scene_detector"] = args.scene_detector
    if getattr(args, "scene_threshold", None) is not None:
        metadata["_scene_threshold"] = args.scene_threshold
    if getattr(args, "num_speakers", None) is not None:
        metadata["_num_speakers"] = args.num_speakers
    if getattr(args, "min_speakers", None) is not None:
        metadata["_min_speakers"] = args.min_speakers
    if getattr(args, "max_speakers", None) is not None:
        metadata["_max_speakers"] = args.max_speakers
    if getattr(args, "visual_model", None):
        metadata["_visual_model"] = args.visual_model
    if getattr(args, "visual_pretrained", None):
        metadata["_visual_pretrained"] = args.visual_pretrained
    if getattr(args, "visual_device", None):
        metadata["_visual_device"] = args.visual_device
    return metadata


def print_result(result, *, json_output: bool = False, include_units: bool = False) -> None:
    if json_output:
        print(json.dumps(result.to_metadata(include_units=include_units), indent=2, sort_keys=True))
        return
    print(f"source: {result.source_ref}")
    print(f"media_type: {result.media_type}")
    print(f"converter: {result.converter_name}@{result.converter_version}")
    print(f"content_hash: {result.content_hash}")
    print(f"artifact_hash: {result.artifact_hash}")
    print(f"parse_quality: {result.parse_quality.score:.3f}")
    print(f"unit_counts: {result.unit_counts}")
    if result.warnings:
        print("warnings:")
        for warning in result.warnings:
            print(f"- {warning}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="Detect source type and converter without mutating Praxis memory.")
    inspect_parser.add_argument("source")
    inspect_parser.add_argument("--json", action="store_true")

    convert_parser = sub.add_parser("convert", help="Convert a source and print normalized extraction metadata.")
    convert_parser.add_argument("source")
    convert_parser.add_argument("--json", action="store_true")
    convert_parser.add_argument("--include-units", action="store_true")
    convert_parser.add_argument("--write-markdown", help="Write extracted text/Markdown to this file.")
    convert_parser.add_argument("--extract-keyframes", action="store_true", help="Extract selected video keyframes when converting media.")
    convert_parser.add_argument("--ocr-keyframes", action="store_true", help="Run OCR over selected keyframes when OCR dependencies are available.")
    convert_parser.add_argument("--visual-embeddings", action="store_true", help="Create visual embedding units using an optional adapter.")
    convert_parser.add_argument("--word-timestamps", action="store_true", help="Request word-level timestamps from speech-to-text adapters.")
    convert_parser.add_argument("--diarize", action="store_true", help="Request speaker diarization from an optional adapter.")
    convert_parser.add_argument("--keyframe-strategy", choices=["interval", "manual", "scene"], default="interval")
    convert_parser.add_argument("--keyframe-every-seconds", type=float, default=30.0)
    convert_parser.add_argument("--keyframe-max-frames", type=int, default=12)
    convert_parser.add_argument("--keyframe-timestamps", action="append", help="Manual keyframe timestamp in seconds or HH:MM:SS.mmm. Repeatable.")
    convert_parser.add_argument("--scene-detector", choices=["content", "adaptive", "threshold"], default="content")
    convert_parser.add_argument("--scene-threshold", type=float, default=27.0)
    convert_parser.add_argument("--num-speakers", type=int)
    convert_parser.add_argument("--min-speakers", type=int)
    convert_parser.add_argument("--max-speakers", type=int)
    convert_parser.add_argument("--visual-model")
    convert_parser.add_argument("--visual-pretrained")
    convert_parser.add_argument("--visual-device")

    keyframes_parser = sub.add_parser("keyframes", help="Convert video with keyframe extraction enabled.")
    keyframes_parser.add_argument("source")
    keyframes_parser.add_argument("--json", action="store_true")
    keyframes_parser.add_argument("--include-units", action="store_true")
    keyframes_parser.add_argument("--ocr", dest="ocr_keyframes", action="store_true", help="Run OCR over extracted keyframes.")
    keyframes_parser.add_argument("--visual-embeddings", action="store_true")
    keyframes_parser.add_argument("--keyframe-strategy", choices=["interval", "manual", "scene"], default="interval")
    keyframes_parser.add_argument("--keyframe-every-seconds", type=float, default=30.0)
    keyframes_parser.add_argument("--keyframe-max-frames", type=int, default=12)
    keyframes_parser.add_argument("--keyframe-timestamps", action="append")
    keyframes_parser.add_argument("--scene-detector", choices=["content", "adaptive", "threshold"], default="content")
    keyframes_parser.add_argument("--scene-threshold", type=float, default=27.0)
    keyframes_parser.add_argument("--visual-model")
    keyframes_parser.add_argument("--visual-pretrained")
    keyframes_parser.add_argument("--visual-device")

    cache_parser = sub.add_parser("cache", help="Inspect and clear cached heavy media artifacts.")
    cache_sub = cache_parser.add_subparsers(dest="cache_command", required=True)
    cache_list = cache_sub.add_parser("list", help="List cached transcripts and keyframes.")
    cache_list.add_argument("--json", action="store_true")
    cache_show = cache_sub.add_parser("show", help="Show a cached media artifact manifest.")
    cache_show.add_argument("cache_id")
    cache_show.add_argument("--json", action="store_true")
    cache_clear = cache_sub.add_parser("clear", help="Clear cached media artifacts.")
    cache_clear.add_argument("--kind", choices=["transcripts", "keyframes"], default="")
    cache_clear.add_argument("--id", dest="cache_id", default="")
    cache_clear.add_argument("--yes", action="store_true", help="Actually delete matching cache entries.")

    doctor_parser = sub.add_parser("doctor", help="Show available intake converters and missing optional dependencies.")
    doctor_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "inspect":
        info = inspect_source(args.source)
        if args.json:
            print(json.dumps(info, indent=2, sort_keys=True))
        else:
            for key, value in info.items():
                print(f"{key}: {value}")
        return 0

    if args.command == "convert":
        result = extract_source(args.source, metadata=media_metadata_from_args(args))
        print_result(result, json_output=args.json, include_units=args.include_units)
        if args.write_markdown:
            path = Path(args.write_markdown)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(result.text + "\n", encoding="utf-8")
            if not args.json:
                print(f"wrote: {path}")
        return 0

    if args.command == "keyframes":
        args.extract_keyframes = True
        result = extract_source(args.source, metadata=media_metadata_from_args(args))
        print_result(result, json_output=args.json, include_units=args.include_units)
        return 0

    if args.command == "doctor":
        rows = converter_doctor()
        if args.json:
            print(json.dumps(rows, indent=2, sort_keys=True))
        else:
            print("Praxis intake converters:")
            for row in rows:
                media = ", ".join(row["media_types"])
                notes = f" ({row['notes']})" if row.get("notes") else ""
                print(f"- {row['converter']}: {row['status']} [{media}]{notes}")
        return 0

    if args.command == "cache":
        root = Path(os.environ.get("PRAXIS_ROOT", ".")).expanduser().resolve() / "intake" / "cache"
        if args.cache_command == "list":
            entries = cache_entries(root)
            if args.json:
                print(json.dumps(entries, indent=2, sort_keys=True))
            elif not entries:
                print("No intake cache entries found.")
            else:
                for entry in entries:
                    detail = f"keyframes={entry.get('keyframe_count', 0)} scenes={entry.get('scene_count', 0)}" if entry["kind"] == "keyframes" else f"text_chars={entry.get('text_chars', 0)}"
                    print(f"{entry['id']} [{entry['kind']}] {detail}")
                    print(f"  path: {entry['path']}")
            return 0
        if args.cache_command == "show":
            shown = cache_entry(root, args.cache_id)
            if shown is None:
                print(f"Cache entry not found: {args.cache_id}")
                return 2
            if args.json:
                print(json.dumps(shown, indent=2, sort_keys=True))
            else:
                entry = shown["entry"]
                print(f"id: {entry['id']}")
                print(f"kind: {entry['kind']}")
                print(f"path: {entry['path']}")
                print(f"warnings: {', '.join(str(w) for w in entry.get('warnings') or [])}")
            return 0
        if args.cache_command == "clear":
            if not args.yes:
                print("Refusing to clear cache without --yes.")
                return 2
            deleted = clear_cache(root, kind=args.kind, entry_id=args.cache_id)
            print(f"Deleted cache entries: {deleted}")
            return 0

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
