# Praxis Intake

Praxis Intake is the source-conversion layer before capture, chunking, search, SkillGraph memory, Reach, or Athens-style traces.

Its job is simple: detect what a source is, convert it into normalized evidence units, record converter metadata, and warn when the extraction is weak.

## Why It Exists

RAG systems often fail before retrieval starts. If a parser flattens tables, drops page numbers, loses slide boundaries, or treats a scanned PDF as text, the rest of the system is working from damaged evidence.

Praxis Intake gives Core a stable contract:

```text
source
-> detect media type
-> select converter
-> extract units
-> score parse quality
-> store evidence metadata
-> chunk / embed / graph / search
```

## Supported Paths

| Source Type | Current Behavior |
| --- | --- |
| Text / Markdown | Extracts the document as searchable text. |
| HTML / web pages | Extracts visible text and removes script/style noise. |
| PDF | Uses optional `pypdf` and preserves page units when available. |
| CSV | Preserves table and row units with structured row data. |
| JSON / JSONL | Preserves structured records and readable JSON text. |
| DOCX / PPTX / XLSX | Uses MarkItDown when installed, otherwise falls back to basic ZIP/XML extraction with warnings. |
| Images | Uses OCR sidecars when present, or optional Pillow + pytesseract OCR when installed. |
| Audio / video | Uses transcript sidecars when present, optional faster-whisper speech-to-text when installed, selected video keyframes when requested, or low-confidence media metadata when no transcript is available. |
| Directories | Captures supported documentation files and records skipped files as warnings. |

## Commands

Inspect a source without changing memory:

```bash
praxis intake inspect ./docs/file.pdf
```

Check converter availability:

```bash
praxis intake doctor
```

Convert and view extraction metadata:

```bash
praxis intake convert ./docs/file.csv
praxis intake convert ./docs/file.csv --json --include-units
praxis intake convert ./demo.mp4 --extract-keyframes --ocr-keyframes --include-units
```

Write extracted Markdown/text:

```bash
praxis intake convert ./docs/file.docx --write-markdown ./tmp/file.md
```

## Optional Dependencies

PDF support:

```bash
python3 -m pip install "praxis-ktos[intake-basic]"
```

Image OCR support:

```bash
python3 -m pip install "praxis-ktos[intake-ocr]"
```

Image OCR may also require a system Tesseract installation. If OCR is not installed, Praxis reports that clearly instead of storing image bytes as fake text.

Stronger Office conversion:

```bash
python3 -m pip install "praxis-ktos[intake-office]"
```

Praxis will use MarkItDown for Office files when it is installed, and fall back to built-in ZIP/XML extraction when it is not.

Local speech-to-text support:

```bash
python3 -m pip install "praxis-ktos[intake-stt]"
```

Praxis uses `faster-whisper` only when audio/video transcription is needed. It is not imported during normal CLI startup. Generated transcripts are cached under the active Praxis root using the media hash and model settings, so the same media file does not need to be transcribed again unless you refresh it.

For media diagnostics, install FFmpeg separately so `ffprobe` and `ffmpeg` are available on your system:

```bash
brew install ffmpeg
```

`ffprobe` is used for media metadata. `faster-whisper` can often decode media directly, but FFmpeg tools make media workflows easier to inspect and debug.

Optional scene, diarization, and visual embedding adapters:

```bash
python3 -m pip install "praxis-ktos[intake-scenes]"
python3 -m pip install "praxis-ktos[intake-diarization]"
python3 -m pip install "praxis-ktos[intake-visual]"
```

These are intentionally separate from the default install. They can be heavy, require model downloads, or require external model access.

If you want all local media extras in one environment:

```bash
python3 -m pip install "praxis-ktos[intake-full-media]"
```

Use this only when you actually need media processing. It can pull in large model/runtime dependencies.

## Sidecar Files

Praxis can ingest media when the searchable text lives next to the source file.

For audio and video, place one of these next to the media file:

```text
demo.mp4.transcript.txt
demo.transcript.txt
demo.transcript.vtt
demo.transcript.srt
demo.vtt
demo.srt
```

For images, place one of these next to the image:

```text
diagram.png.ocr.txt
diagram.ocr.txt
diagram.alt.txt
```

Sidecars are stored as source-linked evidence units. Timestamped `.vtt` and `.srt` files become transcript-segment units with `start` and `end` metadata.

## Audio And Video

Praxis handles audio and video in three levels:

1. **Transcript sidecar**: if a transcript is next to the media file, Praxis uses it with no heavy dependencies.
2. **Optional speech-to-text**: if `praxis-ktos[intake-stt]` is installed, Praxis can generate timestamped transcript units with `faster-whisper`.
3. **Metadata-only fallback**: if no transcript or STT adapter is available, Praxis still records a low-confidence media asset with warnings instead of pretending it extracted searchable speech.

You can choose the default speech-to-text model with environment variables:

```bash
export PRAXIS_STT_MODEL=tiny
export PRAXIS_STT_LANGUAGE=en
```

Start small. Larger speech-to-text models can improve quality but cost more time, memory, and disk.

### Keyframes

Extract selected keyframes from a video:

```bash
praxis intake keyframes ./demo.mp4 --keyframe-every-seconds 30 --keyframe-max-frames 12
```

Use scene-aware keyframes with PySceneDetect:

```bash
praxis intake keyframes ./demo.mp4 --keyframe-strategy scene --scene-detector content --scene-threshold 27
```

Extract keyframes and run OCR over them:

```bash
praxis intake keyframes ./demo.mp4 --ocr --include-units
```

Use manual timestamps:

```bash
praxis intake keyframes ./demo.mp4 --keyframe-strategy manual --keyframe-timestamps 00:01:12.500 --keyframe-timestamps 00:02:05.000
```

Keyframe extraction stores `video_keyframe` units with timestamp, frame path, frame hash, extraction strategy, and warnings. OCR over keyframes stores child `video_frame_text` units linked to the parent keyframe.

Scene-aware extraction also stores `video_scene` units with `start`, `end`, detector, and warning metadata. If PySceneDetect is missing, Praxis reports that clearly instead of pretending interval frames are scene-aware.

### Word Timestamps

Request word-level timestamps from speech-to-text adapters:

```bash
praxis intake convert ./call.wav --word-timestamps --include-units
```

Praxis keeps word timings in structured unit metadata. It does not index every word as its own chunk by default, because that would create noisy memory.

### Diarization And Visual Embeddings

Praxis has evidence-unit contracts for:

- `speaker_turn`;
- `video_scene`;
- `visual_embedding`;
- transcript segments with attached `speaker_id`;
- transcript segments with attached `word_timestamps`.

Speaker diarization is available through the optional pyannote adapter when `praxis-ktos[intake-diarization]` is installed and model access is configured:

```bash
export PYANNOTE_AUTH_TOKEN=...
praxis intake convert ./call.wav --word-timestamps --diarize --min-speakers 2 --max-speakers 6 --include-units
```

Praxis treats speaker labels as provisional turn-taking evidence. `SPEAKER_00` is not a verified person identity unless a user or trusted system maps it later.

Visual embeddings are available through the optional OpenCLIP adapter when `praxis-ktos[intake-visual]` is installed:

```bash
praxis intake keyframes ./demo.mp4 --visual-embeddings --keyframe-strategy scene
```

Visual embeddings are retrieval signals. They should stay linked to source frames, OCR text, timestamps, and source hashes instead of being treated as normal text evidence.

### Media Cache

Heavy media outputs are cached under the active Praxis root so the same artifact does not need to be processed repeatedly.

```bash
praxis intake cache list
praxis intake cache show <cache-id>
praxis intake cache clear --kind transcripts --yes
praxis intake cache clear --kind keyframes --yes
```

Cache entries are keyed by source artifact hash, model/adapter settings, and options. Clearing cache does not delete the original source.

## Parse Quality

Every conversion gets a parse-quality record with:

- score;
- reasons;
- warnings;
- converter name and version;
- media type;
- unit counts;
- source and artifact hashes.

Parse quality is not a truth score. It is a warning about whether the source was converted cleanly enough to use downstream.

## Current Limits

Office extraction is adapter-based. MarkItDown improves the default path when installed, but complex tables, comments, formulas, charts, speaker notes, and visual relationships still need verification.

Audio/video transcription is optional and local. Interval/manual keyframe extraction is available through FFmpeg when requested. Scene-aware keyframes use PySceneDetect when installed. Diarization uses pyannote when installed and configured. Visual embeddings use OpenCLIP when installed. None of these heavy adapters are imported during normal CLI startup.

For production-heavy document AI, Praxis should eventually support optional advanced adapters such as Docling, Unstructured, OCR/VLM extraction, and parser benchmarking. The stable part is the Praxis evidence-unit contract, not any one parser.
