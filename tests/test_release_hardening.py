from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from praxis.context_priority import score_context_priority
from praxis.intake import extract_source
from praxis.intake.registry import convert_bytes


def copy_fixture(source: str, root: Path) -> None:
    src = REPO / "bootstrap" / source
    if not src.exists():
        src = REPO / source
    dst = root / "bootstrap" / source if source in {
        "db/schema.sql",
        "kg/schema.sql",
        "kg/seed_graph.json",
        "sources/seed_sources.json",
    } else root / source
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def ws(root: Path, *parts: str) -> Path:
    return root.joinpath("workspace", *parts)


def make_root(tempdir: str) -> Path:
    root = Path(tempdir)
    for path in [
        "bootstrap/db",
        "bootstrap/kg",
        "bootstrap/sources",
        "workspace/db",
        "workspace/kg",
        "workspace/research/captures",
        "workspace/research/proposals",
        "workspace/research/applied",
        "workspace/research/rejected",
        "workspace/research/inbox",
        "workspace/sources",
        "workspace/vectors",
        "workspace/watchlists",
        "workspace/exports",
        "workspace/notes",
    ]:
        (root / path).mkdir(parents=True, exist_ok=True)
    for fixture in [
        "db/schema.sql",
        "kg/schema.sql",
        "kg/seed_graph.json",
        "sources/seed_sources.json",
    ]:
        copy_fixture(fixture, root)
    return root


def run_praxis(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO / "src")
    env["PYTHONPYCACHEPREFIX"] = str(root / ".pycache")
    result = subprocess.run(
        [sys.executable, "-m", "praxis", "--root", str(root), *args],
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(f"praxis {' '.join(args)} failed with {result.returncode}\n{result.stdout}")
    return result


def init_root(root: Path) -> None:
    run_praxis(root, "init-db")
    run_praxis(root, "init-graph")


def write_source(root: Path) -> Path:
    source = ws(root, "notes", "semantic-contracts.md")
    source.write_text(
        "\n".join(
            [
                "# Semantic Contract Test Source",
                "",
                "Agents should use a task semantic contract before parallel work starts.",
                "The contract records assumptions, acceptance criteria, dependencies, and intended outputs.",
                "The runtime should support reasoning branch merge, context distillation, and divergence detection.",
                "Rollback and audit logs keep provisional graph updates reversible.",
            ]
        ),
        encoding="utf-8",
    )
    return source


def write_minimal_docx(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", document_xml)


def change_set_from(output: str) -> str:
    match = re.search(r"change_set_id:\s*(chg:[^\s]+)", output)
    if not match:
        raise AssertionError(f"No change_set_id found in output:\n{output}")
    return match.group(1)


def conflict_from(output: str, conflict_type: str) -> str:
    match = re.search(rf"(conflict:{re.escape(conflict_type)}:[^\s]+)", output)
    if not match:
        raise AssertionError(f"No {conflict_type} conflict found in output:\n{output}")
    return match.group(1)


class ReleaseHardeningTests(unittest.TestCase):
    def test_intake_extracts_structured_csv_units(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            source = ws(root, "notes", "gtm-segments.csv")
            source.write_text(
                "segment,region,title\ntrade schools,Pacific Northwest,Director of Student Housing\ncommunity colleges,South,VP Student Services\n",
                encoding="utf-8",
            )

            result = extract_source(str(source))

            self.assertEqual("text/csv", result.media_type)
            self.assertEqual("csv", result.converter_name)
            self.assertEqual(1, result.unit_counts["table"])
            self.assertEqual(2, result.unit_counts["table_row"])
            self.assertGreater(result.parse_quality.score, 0.4)
            self.assertIn("Director of Student Housing", result.text)
            self.assertTrue(any(unit.structured_data for unit in result.units if unit.unit_type == "table_row"))

    def test_intake_cli_inspects_and_converts_docx(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            source = ws(root, "notes", "brief.docx")
            write_minimal_docx(source, "Praxis intake preserves document evidence.")

            inspected = run_praxis(root, "intake", "inspect", str(source))
            self.assertIn("converter: docx-office", inspected.stdout)

            converted = run_praxis(root, "intake", "convert", str(source))
            self.assertIn("converter: docx", converted.stdout)
            self.assertIn("parse_quality:", converted.stdout)

    def test_intake_uses_video_transcript_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            video = ws(root, "notes", "demo.mp4")
            video.write_bytes(b"not a real video but enough for media detection")
            sidecar = ws(root, "notes", "demo.transcript.vtt")
            sidecar.write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nPraxis can ingest transcript sidecars.\n\n00:00:05.000 --> 00:00:08.000\nThe source media stays attached.\n",
                encoding="utf-8",
            )

            inspected = run_praxis(root, "intake", "inspect", str(video))
            self.assertIn("converter: video-transcript-sidecar", inspected.stdout)

            result = extract_source(str(video))
            self.assertEqual("video-transcript-sidecar", result.converter_name)
            self.assertEqual(2, result.unit_counts["video_transcript_segment"])
            self.assertIn("Praxis can ingest transcript sidecars", result.text)
            self.assertEqual(str(sidecar), result.metadata["sidecar_path"])

    def test_intake_media_without_stt_archives_metadata_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            video = ws(root, "notes", "demo.mp4")
            video.write_bytes(b"not a real video but enough for media detection")

            result = extract_source(str(video))

            self.assertEqual("video-media", result.converter_name)
            self.assertEqual(1, result.unit_counts["video_asset"])
            self.assertIn("Media kind: video", result.text)
            self.assertTrue(any("no_transcript_extracted" in warning for warning in result.warnings))
            self.assertLess(result.parse_quality.score, 0.4)

    def test_intake_fake_stt_generates_timestamped_units_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            audio = ws(root, "notes", "call.wav")
            body = b"fake wav body"
            audio.write_bytes(body)
            calls = {"count": 0}

            def fake_stt(_source_ref: str, _options: dict) -> tuple[str, dict, list[str]]:
                calls["count"] += 1
                return (
                    "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nPraxis can generate transcript evidence.\n",
                    {"stt_model": "fake-model"},
                    ["fake_stt_used"],
                )

            previous_root = os.environ.get("PRAXIS_ROOT")
            os.environ["PRAXIS_ROOT"] = str(root)
            try:
                first = convert_bytes(
                    str(audio),
                    body,
                    media_type="audio/wav",
                    metadata={"path": str(audio), "_stt_adapter": fake_stt, "_stt_model": "fake-model"},
                )
                second = convert_bytes(
                    str(audio),
                    body,
                    media_type="audio/wav",
                    metadata={"path": str(audio), "_stt_model": "fake-model"},
                )
            finally:
                if previous_root is None:
                    os.environ.pop("PRAXIS_ROOT", None)
                else:
                    os.environ["PRAXIS_ROOT"] = previous_root

            self.assertEqual(1, calls["count"])
            self.assertEqual("audio-stt", first.converter_name)
            self.assertEqual("audio-stt", second.converter_name)
            self.assertEqual(1, first.unit_counts["audio_transcript_segment"])
            self.assertIn("Praxis can generate transcript evidence", second.text)
            self.assertEqual("hit", second.metadata["transcript_cache_status"])
            self.assertTrue(Path(second.metadata["transcript_cache_path"]).exists())

            listed = run_praxis(root, "intake", "cache", "list")
            self.assertIn("[transcripts]", listed.stdout)
            self.assertIn("text_chars=", listed.stdout)
            shown = run_praxis(root, "intake", "cache", "show", Path(second.metadata["transcript_cache_path"]).stem)
            self.assertIn("kind: transcripts", shown.stdout)
            refused = run_praxis(root, "intake", "cache", "clear", "--kind", "transcripts", check=False)
            self.assertEqual(2, refused.returncode, refused.stdout)
            cleared = run_praxis(root, "intake", "cache", "clear", "--kind", "transcripts", "--yes")
            self.assertIn("Deleted cache entries: 1", cleared.stdout)

    def test_intake_word_timestamps_and_diarization_attach_to_transcript_units(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            audio = ws(root, "notes", "interview.wav")
            body = b"fake interview body"
            audio.write_bytes(body)

            def fake_stt(_source_ref: str, _options: dict) -> tuple[str, dict, list[str]]:
                return (
                    "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nWe should preserve media evidence.\n",
                    {
                        "stt_model": "fake-model",
                        "word_timestamps": [
                            {"word": "We", "start": 1.0, "end": 1.2, "probability": 0.99},
                            {"word": "should", "start": 1.21, "end": 1.6, "probability": 0.98},
                        ],
                    },
                    [],
                )

            def fake_diarization(_source_ref: str, _metadata: dict) -> tuple[list[dict], dict, list[str]]:
                return ([{"speaker_id": "speaker_a", "start": 0.5, "end": 3.5, "confidence": "medium"}], {"diarization_model": "fake"}, [])

            previous_root = os.environ.get("PRAXIS_ROOT")
            os.environ["PRAXIS_ROOT"] = str(root)
            try:
                result = convert_bytes(
                    str(audio),
                    body,
                    media_type="audio/wav",
                    metadata={
                        "path": str(audio),
                        "_stt_adapter": fake_stt,
                        "_stt_model": "fake-word-model",
                        "_word_timestamps": True,
                        "_diarize": True,
                        "_diarization_adapter": fake_diarization,
                    },
                )
            finally:
                if previous_root is None:
                    os.environ.pop("PRAXIS_ROOT", None)
                else:
                    os.environ["PRAXIS_ROOT"] = previous_root

            transcript = next(unit for unit in result.units if unit.unit_type == "audio_transcript_segment")
            self.assertEqual("speaker_a", transcript.structured_data["speaker_id"])
            self.assertEqual("We", transcript.structured_data["word_timestamps"][0]["word"])
            self.assertEqual(1, result.unit_counts["speaker_turn"])

    def test_intake_keyframes_ocr_and_visual_embeddings_use_optional_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            video = ws(root, "notes", "demo.mp4")
            body = b"fake video body"
            video.write_bytes(body)

            def fake_keyframes(_source_ref: str, _options: dict) -> tuple[list[dict], dict, list[str]]:
                return (
                    [{"timestamp": 2.5, "bytes": b"fake jpg bytes", "extension": ".jpg", "metadata": {"scene_id": "scene_1"}}],
                    {
                        "keyframe_adapter": "fake",
                        "scenes": [
                            {"start": 1.0, "end": 4.0, "detector": "fake-scene", "metadata": {"midpoint": 2.5}}
                        ],
                    },
                    [],
                )

            def fake_ocr(_source_ref: str, _image_bytes: bytes, _metadata: dict) -> tuple[str, dict, list[str]]:
                return ("Slide says retention dashboard and student housing.", {"ocr_engine": "fake"}, [])

            def fake_visual(_source_ref: str, _image_bytes: bytes, _metadata: dict) -> tuple[list[float], dict, list[str]]:
                return ([0.1, 0.2, 0.3], {"embedding_model": "fake-clip"}, [])

            previous_root = os.environ.get("PRAXIS_ROOT")
            os.environ["PRAXIS_ROOT"] = str(root)
            try:
                result = convert_bytes(
                    str(video),
                    body,
                    media_type="video/mp4",
                    metadata={
                        "path": str(video),
                        "_extract_keyframes": True,
                        "_ocr_keyframes": True,
                        "_visual_embeddings": True,
                        "_keyframe_adapter": fake_keyframes,
                        "_ocr_adapter": fake_ocr,
                        "_visual_embedding_adapter": fake_visual,
                    },
                )
            finally:
                if previous_root is None:
                    os.environ.pop("PRAXIS_ROOT", None)
                else:
                    os.environ["PRAXIS_ROOT"] = previous_root

            self.assertEqual("video-keyframes", result.converter_name)
            self.assertEqual(1, result.unit_counts["video_scene"])
            self.assertEqual(1, result.unit_counts["video_keyframe"])
            self.assertEqual(1, result.unit_counts["video_frame_text"])
            self.assertEqual(1, result.unit_counts["visual_embedding"])
            self.assertIn("retention dashboard", result.text)
            scene = next(unit for unit in result.units if unit.unit_type == "video_scene")
            self.assertEqual("derived", scene.structured_data["evidence_lifecycle"])
            self.assertEqual("fake-scene", scene.structured_data["detector"])
            frame = next(unit for unit in result.units if unit.unit_type == "video_keyframe")
            self.assertEqual("custom", frame.structured_data["adapter_name"])
            self.assertIn("not full video understanding", frame.structured_data["confidence_reason"])
            visual = next(unit for unit in result.units if unit.unit_type == "visual_embedding")
            self.assertEqual([0.1, 0.2, 0.3], visual.structured_data["vector"])

    def test_intake_uses_image_ocr_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            image = ws(root, "notes", "diagram.png")
            image.write_bytes(b"not a real image but enough for media detection")
            sidecar = ws(root, "notes", "diagram.ocr.txt")
            sidecar.write_text("Diagram text extracted by an external OCR step.", encoding="utf-8")

            result = extract_source(str(image))

            self.assertEqual("image-ocr-sidecar", result.converter_name)
            self.assertEqual(1, result.unit_counts["image_text"])
            self.assertIn("external OCR", result.text)
            self.assertEqual(str(sidecar), result.metadata["sidecar_path"])

    def test_capture_records_intake_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            init_root(root)
            source = ws(root, "notes", "segments.csv")
            source.write_text("segment,signal\ntrade schools,housing\n", encoding="utf-8")

            run_praxis(root, "capture", str(source), "--source-type", "docs")

            with sqlite3.connect(ws(root, "kg", "skill_graph.sqlite")) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute("SELECT metadata_json FROM source_captures ORDER BY created_at DESC LIMIT 1").fetchone()
            metadata = json.loads(row["metadata_json"])
            self.assertEqual("csv", metadata["intake"]["converter_name"])
            self.assertEqual("text/csv", metadata["intake"]["media_type"])
            self.assertIn("parse_quality", metadata["intake"])
            self.assertTrue(Path(metadata["artifact_path"]).exists())

    def test_intake_doctor_reports_optional_pdf_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)

            result = run_praxis(root, "intake", "doctor")

            self.assertIn("Praxis intake converters:", result.stdout)
            self.assertIn("pdf-pypdf:", result.stdout)

    def test_context_priority_penalizes_stale_or_conflicted_context(self) -> None:
        row = {"confidence": "high", "status": "active"}
        fresh_source = {
            "credibility_score": 4,
            "status": "active",
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
            "freshness_window_days": 30,
        }
        stale_source = {
            "credibility_score": 4,
            "status": "active",
            "last_checked_at": "2024-01-01T00:00:00+00:00",
            "freshness_window_days": 30,
        }

        clean = score_context_priority(relevance=0.8, row=row, source=fresh_source, graph=0.3, conflicts=[])
        stale = score_context_priority(relevance=0.8, row=row, source=stale_source, graph=0.3, conflicts=[])
        conflicted = score_context_priority(
            relevance=0.8,
            row=row,
            source=fresh_source,
            graph=0.3,
            conflicts=[{"severity": "high", "status": "open"}],
        )

        self.assertGreater(clean.priority, stale.priority)
        self.assertGreater(clean.priority, conflicted.priority)
        self.assertGreater(conflicted.conflict_penalty, 0.0)
        self.assertTrue(any("freshness:stale" in reason for reason in stale.reasons))

    def test_ingest_initializes_missing_skill_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            source = write_source(root)

            ingest = run_praxis(root, "ingest", str(source), "--source-type", "docs", "--risk-level", "low")

            self.assertIn("Ingested Semantic Contract Test Source", ingest.stdout)
            self.assertIn("change_set_id:", ingest.stdout)

    def test_ingest_promote_deprecate_and_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            init_root(root)
            source = write_source(root)

            ingest = run_praxis(root, "ingest", str(source), "--source-type", "docs", "--risk-level", "low")
            change_set = change_set_from(ingest.stdout)

            provisional = run_praxis(root, "graph", "search", "Semantic Contract Test Source")
            self.assertIn("status: provisional", provisional.stdout)

            promoted = run_praxis(root, "promote", change_set)
            self.assertIn("Objects changed:", promoted.stdout)
            active = run_praxis(root, "graph", "search", "Semantic Contract Test Source")
            self.assertIn("status: active", active.stdout)

            deprecated = run_praxis(root, "deprecate", change_set)
            self.assertIn("Objects changed:", deprecated.stdout)
            hidden = run_praxis(root, "graph", "search", "Semantic Contract Test Source")
            self.assertIn("No matching nodes.", hidden.stdout)

            inactive = run_praxis(root, "graph", "--include-inactive", "search", "Semantic Contract Test Source")
            self.assertIn("status: deprecated", inactive.stdout)

    def test_rollback_refuses_after_later_change_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            init_root(root)
            source = write_source(root)

            ingest = run_praxis(root, "ingest", str(source), "--source-type", "docs", "--risk-level", "low")
            change_set = change_set_from(ingest.stdout)
            run_praxis(root, "promote", change_set)

            refused = run_praxis(root, "rollback", change_set, check=False)
            self.assertEqual(2, refused.returncode, refused.stdout)
            self.assertIn("Refusing rollback", refused.stdout)
            self.assertIn("Use --force", refused.stdout)

            forced = run_praxis(root, "rollback", change_set, "--force")
            self.assertIn("Rolled back change set", forced.stdout)
            hidden = run_praxis(root, "graph", "search", "Semantic Contract Test Source")
            self.assertIn("No matching nodes.", hidden.stdout)

    def test_search_explain_prints_score_and_source_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            init_root(root)
            source = write_source(root)

            run_praxis(root, "ingest", str(source), "--source-type", "docs", "--risk-level", "low")
            run_praxis(root, "chunk", "--reset", "--no-runtimes", "--no-skills")
            run_praxis(root, "embed", "--provider", "local-hash")

            result = run_praxis(root, "search", "task semantic contract", "--limit", "3", "--explain")
            self.assertIn("explain:", result.stdout)
            self.assertIn("priority_breakdown:", result.stdout)
            self.assertIn("priority_reasons:", result.stdout)
            self.assertIn("source_id:", result.stdout)
            self.assertIn("graph_hints_used:", result.stdout)

    def test_auto_chunking_preserves_document_structure_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            source = ws(root, "notes", "production-rag.md")
            source.write_text(
                "\n".join(
                    [
                        "# Production RAG",
                        "",
                        "Chunking should follow semantic boundaries instead of arbitrary token windows.",
                        "Good retrieval depends on coherent units of meaning.",
                        "",
                        "## Retrieval Metrics",
                        "",
                        "| Metric | Meaning |",
                        "| --- | --- |",
                        "| recall | whether the right evidence appears |",
                        "| precision | whether irrelevant evidence is suppressed |",
                        "",
                        "## Example Code",
                        "",
                        "```python",
                        "def chunk_document(text):",
                        "    return text.split('\\n\\n')",
                        "```",
                        "",
                        "## Notes",
                        "",
                        "Overlap helps continuity, but it is not a substitute for respecting headings, tables, and code blocks.",
                    ]
                ),
                encoding="utf-8",
            )

            run_praxis(
                root,
                "chunk",
                "--reset",
                "--no-runtimes",
                "--no-skills",
                "--target-chars",
                "360",
                "--overlap-chars",
                "80",
            )

            with sqlite3.connect(ws(root, "vectors", "semantic_index.sqlite")) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT section, text, metadata_json
                    FROM semantic_chunks
                    WHERE title = ?
                    ORDER BY chunk_index
                    """,
                    ("Production RAG",),
                ).fetchall()

            self.assertGreaterEqual(len(rows), 2)
            metadata = [json.loads(row["metadata_json"]) for row in rows]
            self.assertTrue(all(item["chunking_strategy"] == "markdown" for item in metadata))
            self.assertTrue(any("table" in item["block_types"] for item in metadata))
            self.assertTrue(any("code_block" in item["block_types"] for item in metadata))
            self.assertTrue(any("markdown heading boundary" in " ".join(item["boundary_rationale"]) for item in metadata))
            self.assertTrue(any(item["parent_context"].startswith("Production RAG") for item in metadata))
            self.assertTrue(any(item.get("previous_context") for item in metadata[1:]))
            self.assertTrue(any("    return text.split" in row["text"] for row in rows))

    def test_duplicate_content_conflict_can_be_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            source = write_source(root)

            run_praxis(root, "ingest", str(source), "--source-id", "src:duplicate-a", "--title", "Duplicate A", "--source-type", "docs", "--risk-level", "low")
            second = run_praxis(root, "ingest", str(source), "--source-id", "src:duplicate-b", "--title", "Duplicate B", "--source-type", "docs", "--risk-level", "low")
            second_change_set = change_set_from(second.stdout)
            self.assertIn("conflict_warnings:", second.stdout)

            listed = run_praxis(root, "conflicts", "list", "--type", "duplicate_content")
            conflict_id = conflict_from(listed.stdout, "duplicate_content")
            shown = run_praxis(root, "conflicts", "show", conflict_id)
            self.assertIn("Duplicate captured content hash", shown.stdout)

            run_praxis(root, "chunk", "--reset", "--no-runtimes", "--no-skills")
            run_praxis(root, "embed", "--provider", "local-hash")
            search = run_praxis(root, "search", "semantic contract", "--limit", "2", "--explain")
            self.assertIn("conflict_warnings:", search.stdout)
            self.assertIn("conflict_penalty=", search.stdout)

            refused_export = run_praxis(root, "export-graph", "--fail-on-open-conflicts", check=False)
            self.assertEqual(2, refused_export.returncode, refused_export.stdout)
            self.assertIn("Refusing export", refused_export.stdout)

            resolved = run_praxis(root, "conflicts", "resolve", conflict_id, "--resolution", "keep_both_with_scope", "--notes", "test")
            self.assertIn("status: resolved", resolved.stdout)
            open_list = run_praxis(root, "conflicts", "list", "--type", "duplicate_content")
            self.assertIn("No conflicts found.", open_list.stdout)
            rescanned = run_praxis(root, "conflicts", "scan", second_change_set)
            self.assertIn("Conflicts found:", rescanned.stdout)
            reopened = run_praxis(root, "conflicts", "list", "--type", "duplicate_content")
            reopened_conflict = conflict_from(reopened.stdout, "duplicate_content")
            reopened_shown = run_praxis(root, "conflicts", "show", reopened_conflict)
            self.assertIn("previous_conflict_id", reopened_shown.stdout)

    def test_claim_contradiction_is_logged(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            init_root(root)
            first = ws(root, "research", "proposals", "use-sqlite.json")
            second = ws(root, "research", "proposals", "avoid-sqlite.json")
            first.write_text(
                json.dumps(
                    {
                        "id": "proposal:use-sqlite",
                        "title": "Use SQLite",
                        "risk_level": "low",
                        "summary": "Positive claim.",
                        "nodes": [
                            {
                                "id": "claim:use-sqlite",
                                "type": "claim",
                                "name": "Use SQLite",
                                "summary": "Use SQLite for local memory.",
                                "confidence": "medium",
                                "status": "provisional",
                            }
                        ],
                        "edges": [],
                        "evidence": [],
                    }
                ),
                encoding="utf-8",
            )
            second.write_text(
                json.dumps(
                    {
                        "id": "proposal:avoid-sqlite",
                        "title": "Avoid SQLite",
                        "risk_level": "low",
                        "summary": "Negative claim.",
                        "nodes": [
                            {
                                "id": "claim:avoid-sqlite",
                                "type": "claim",
                                "name": "Avoid SQLite",
                                "summary": "Avoid SQLite for local memory.",
                                "confidence": "medium",
                                "status": "provisional",
                            }
                        ],
                        "edges": [],
                        "evidence": [],
                    }
                ),
                encoding="utf-8",
            )

            run_praxis(root, "apply", str(first))
            applied = run_praxis(root, "apply", str(second))
            self.assertIn("Conflict warnings:", applied.stdout)
            listed = run_praxis(root, "conflicts", "list", "--type", "contradiction")
            self.assertIn("Possible contradiction", listed.stdout)

    def test_duplicate_entity_merge_and_split_are_reversible(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            first = ws(root, "notes", "jack.md")
            second = ws(root, "notes", "dr-jack.md")
            first.write_text("# Jack Abbott\n\nJack Abbott is an example entity for dedupe testing.\n", encoding="utf-8")
            second.write_text("# Dr. Jack Abbott\n\nDr. Jack Abbott is the same example entity for dedupe testing.\n", encoding="utf-8")

            run_praxis(root, "ingest", str(first), "--source-type", "docs", "--risk-level", "low")
            run_praxis(root, "ingest", str(second), "--source-type", "docs", "--risk-level", "low")

            listed = run_praxis(root, "dedupe", "list")
            conflict_id = conflict_from(listed.stdout, "duplicate_entity")
            merged = run_praxis(root, "dedupe", "merge", conflict_id, "--canonical", "external:jack-abbott")
            merge_change_set = change_set_from(merged.stdout)

            with sqlite3.connect(ws(root, "kg", "skill_graph.sqlite")) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute("SELECT status FROM nodes WHERE id = 'external:dr-jack-abbott'").fetchone()
                self.assertEqual("merged", row["status"])

            split = run_praxis(root, "dedupe", "split", merge_change_set)
            self.assertIn("Reverted dedupe merge", split.stdout)
            self.assertIn("Reopened dedupe conflicts: 1", split.stdout)
            with sqlite3.connect(ws(root, "kg", "skill_graph.sqlite")) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute("SELECT status FROM nodes WHERE id = 'external:dr-jack-abbott'").fetchone()
                self.assertEqual("provisional", row["status"])

    def test_bootstrap_assets_initialize_workspace_databases(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = make_root(tempdir)
            run_praxis(root, "init-db")
            run_praxis(root, "init-graph")

            self.assertTrue(ws(root, "db", "praxis.sqlite").exists())
            self.assertTrue(ws(root, "kg", "skill_graph.sqlite").exists())

    def test_migrate_workspace_plan_and_apply_do_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            legacy_file = root / "research" / "captures" / "legacy.raw.txt"
            legacy_file.parent.mkdir(parents=True, exist_ok=True)
            legacy_file.write_text("legacy capture", encoding="utf-8")
            target_file = ws(root, "research", "captures", "existing.raw.txt")
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text("keep me", encoding="utf-8")
            conflicting_legacy = root / "research" / "captures" / "existing.raw.txt"
            conflicting_legacy.write_text("do not overwrite", encoding="utf-8")

            plan = run_praxis(root, "migrate-workspace", "--plan")
            self.assertIn("move: research/captures/legacy.raw.txt", plan.stdout)
            self.assertIn("skip: research/captures/existing.raw.txt", plan.stdout)
            self.assertTrue(legacy_file.exists())

            applied = run_praxis(root, "migrate-workspace", "--apply")
            self.assertIn("applied: 1 move(s), 1 skip(s)", applied.stdout)
            self.assertTrue(ws(root, "research", "captures", "legacy.raw.txt").exists())
            self.assertEqual("keep me", target_file.read_text(encoding="utf-8"))
            self.assertTrue(conflicting_legacy.exists())

    def test_workspace_generated_databases_are_git_ignored(self) -> None:
        result = subprocess.run(
            ["git", "check-ignore", "workspace/db/praxis.sqlite", "workspace/kg/skill_graph.sqlite", "workspace/vectors/semantic_index.sqlite"],
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout)


if __name__ == "__main__":
    unittest.main()
