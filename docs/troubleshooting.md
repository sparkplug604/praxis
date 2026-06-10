# Troubleshooting

This page covers the most common first-run issues.

## `praxis` Is Not Recognized

This usually means Python installed the command into a Scripts/bin directory that is not on your PATH.

Use the module form:

```bash
python3 -m praxis --help
python3 -m praxis setup
```

Windows PowerShell:

```powershell
py -m praxis --help
py -m praxis setup
```

Important: Praxis commands are subcommands. Use:

```powershell
py -m praxis ingest "https://example.com/source"
```

Do not run `ingest` by itself.

## `No module named praxis`

Install Praxis from the checkout:

```bash
python3 -m pip install -e .
```

Windows PowerShell:

```powershell
py -m pip install -e .
```

If you do not want to install, run from the checkout with `PYTHONPATH`:

```bash
PYTHONPATH=src python3 -m praxis --help
```

PowerShell:

```powershell
$env:PYTHONPATH = "src"
py -m praxis --help
```

## `no such table: source_registry`

The local SQLite databases have not been initialized yet.

Run:

```bash
praxis bootstrap
praxis doctor --require-index
```

If you only need Reach/Agency fixture demos, run:

```bash
praxis reach init
```

## The Setup Wizard Fails Halfway Through

Re-run the same setup path. Fixture setup uses `--overwrite` for demo clients, so it is safe to repeat:

```bash
praxis setup --non-interactive --path reach-demo
```

If a generated artifact looks stale, inspect it before deleting anything:

```bash
praxis reach evidence list --client demo
praxis agency client show demo
praxis reach stale list --client demo --all
```

## Live Connector Credentials Are Missing

Reach fixture demos do not need credentials. Live connectors do.

HubSpot:

```bash
praxis reach connectors test hubspot --client acme
```

Google Ads:

```bash
praxis reach connectors test google_ads --client acme
```

Google Analytics:

```bash
praxis reach connectors test google_analytics --client acme
```

The connector test output tells you which environment variable is missing.

## Search Returns Nothing

Check that sources were chunked and embedded:

```bash
praxis doctor --require-index
praxis chunk --changed-only
praxis embed --provider local-hash
praxis search "your query" --explain
```

`local-hash` embeddings are offline and credential-free. They are good for setup and demos. For production-quality semantic ranking, configure a real embedding provider later.

## PDF, DOCX, Images, Audio, Or Video Do Not Ingest

Check what Praxis thinks the source is:

```bash
praxis intake inspect ./your-file.pdf
praxis intake doctor
```

PDF extraction needs the intake PDF extra:

```bash
python3 -m pip install "praxis-ktos[intake-basic]"
```

Images can use OCR sidecars such as `diagram.ocr.txt` or `diagram.png.ocr.txt`. If you want Praxis to run OCR directly, install OCR dependencies:

```bash
python3 -m pip install "praxis-ktos[intake-ocr]"
```

Audio and video can use transcript sidecars such as `demo.transcript.vtt`, `demo.transcript.srt`, or `demo.mp4.transcript.txt`. If you want Praxis to generate transcripts locally, install the optional speech-to-text extra:

```bash
python3 -m pip install "praxis-ktos[intake-stt]"
```

Praxis will still archive media as low-confidence metadata when no transcript or speech-to-text adapter is available. Use `praxis intake doctor` to check `ffprobe`, `ffmpeg`, `stt-faster-whisper`, keyframe, diarization, and visual embedding adapter availability.

For video keyframes, install FFmpeg and run:

```bash
praxis intake keyframes ./demo.mp4 --keyframe-every-seconds 30 --keyframe-max-frames 12
```

For scene-aware keyframes, install the scene extra and run:

```bash
python3 -m pip install "praxis-ktos[intake-scenes]"
praxis intake keyframes ./demo.mp4 --keyframe-strategy scene
```

If `--ocr` returns no `video_frame_text` units, check OCR dependencies with `praxis intake doctor` and verify the selected frames actually contain readable text.

If `--diarize` fails, check that `pyannote.audio` is installed and that one of these environment variables is set:

```bash
PYANNOTE_AUTH_TOKEN
HUGGINGFACE_TOKEN
HF_TOKEN
```

For privacy-conscious runs, review pyannote model access requirements and consider setting:

```bash
PYANNOTE_METRICS_ENABLED=0
```

If media processing keeps repeating, inspect the cache:

```bash
praxis intake cache list
praxis intake cache show <cache-id>
```

Clear only derived cache artifacts, not original sources:

```bash
praxis intake cache clear --kind keyframes --yes
```

For stronger Office file conversion:

```bash
python3 -m pip install "praxis-ktos[intake-office]"
```

If a file converts but search results are poor, inspect parse quality:

```bash
praxis intake convert ./your-file.pdf --json
```

Low parse quality usually means the parser lost structure, extracted very little text, or needs OCR.

## Windows Path And Quoting Tips

Use quotes around URLs:

```powershell
py -m praxis ingest "https://example.com/source"
```

Run commands from the Praxis checkout unless you pass `--root`:

```powershell
py -m praxis --root "C:\Users\you\praxis" doctor --require-index
```

If PowerShell wraps long URLs across lines, keep the URL in one quoted string.
