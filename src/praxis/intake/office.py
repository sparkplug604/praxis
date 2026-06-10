"""Office document converters for Praxis intake."""

from __future__ import annotations

import io
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .models import ExtractedUnit, UnsupportedMediaError
from .structured import _markdown_table
from .units import make_unit


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_text(xml_bytes: bytes) -> str:
    root = ElementTree.fromstring(xml_bytes)
    parts: list[str] = []
    for elem in root.iter():
        if _local_name(elem.tag) == "t" and elem.text:
            parts.append(elem.text)
        elif _local_name(elem.tag) in {"p", "tr"} and parts and parts[-1] != "\n":
            parts.append("\n")
    raw = " ".join(part for part in parts if part != "\n")
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _try_markitdown(source_ref: str, body: bytes, metadata: dict[str, Any], *, unit_type: str) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]] | None:
    try:
        from markitdown import MarkItDown
    except Exception:
        return None

    suffix = Path(source_ref).suffix or ".bin"
    temp_path: str | None = None
    try:
        path = metadata.get("path")
        if path and Path(str(path)).exists():
            convert_path = str(path)
        else:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                handle.write(body)
                temp_path = handle.name
            convert_path = temp_path
        converted = MarkItDown().convert(convert_path)
        text = getattr(converted, "text_content", "") or str(converted)
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink()
            except OSError:
                pass
    if not text.strip():
        return None
    metadata = {**metadata, "_converter_name": f"{unit_type}-markitdown", "office_adapter": "markitdown"}
    warnings = ["office_markitdown_extraction; verify complex tables, comments, and visual layout before trusting derived memory"]
    return [make_unit(source_ref, f"{unit_type}_document", text, location={"source": source_ref}, warnings=warnings)], metadata, warnings


def convert_docx(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    markitdown = _try_markitdown(source_ref, body, metadata, unit_type="docx")
    if markitdown:
        return markitdown
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            xml_bytes = archive.read("word/document.xml")
    except Exception as exc:
        raise UnsupportedMediaError(f"Could not read DOCX structure: {exc}") from exc
    text = _xml_text(xml_bytes)
    warnings = ["docx_basic_xml_extraction; advanced layout and comments are not preserved"]
    return [make_unit(source_ref, "docx_document", text, location={"source": source_ref}, warnings=warnings)], metadata, warnings


def convert_pptx(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    markitdown = _try_markitdown(source_ref, body, metadata, unit_type="pptx")
    if markitdown:
        return markitdown
    units: list[ExtractedUnit] = []
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            slide_names = sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
            for index, name in enumerate(slide_names, 1):
                text = _xml_text(archive.read(name))
                if text.strip():
                    units.append(make_unit(source_ref, "slide", text, index=index, markdown=f"## Slide {index}\n\n{text}", location={"slide": index}))
    except Exception as exc:
        raise UnsupportedMediaError(f"Could not read PPTX structure: {exc}") from exc
    warnings = ["pptx_basic_xml_extraction; speaker notes and visual layout are not preserved"]
    return units, {**metadata, "pptx_slides": len(units)}, warnings


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for item in root:
        texts = [elem.text or "" for elem in item.iter() if _local_name(elem.tag) == "t"]
        values.append("".join(texts))
    return values


def convert_xlsx(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    markitdown = _try_markitdown(source_ref, body, metadata, unit_type="xlsx")
    if markitdown:
        return markitdown
    units: list[ExtractedUnit] = []
    warnings = ["xlsx_basic_xml_extraction; formulas, formatting, charts, and hidden state are not preserved"]
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            shared = _xlsx_shared_strings(archive)
            sheets = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
            for sheet_index, sheet_name in enumerate(sheets, 1):
                root = ElementTree.fromstring(archive.read(sheet_name))
                rows: list[list[str]] = []
                for row in root.iter():
                    if _local_name(row.tag) != "row":
                        continue
                    values: list[str] = []
                    for cell in row:
                        if _local_name(cell.tag) != "c":
                            continue
                        cell_type = cell.attrib.get("t")
                        value = ""
                        for child in cell:
                            if _local_name(child.tag) == "v" and child.text is not None:
                                value = child.text
                                break
                        if cell_type == "s" and value.isdigit() and int(value) < len(shared):
                            value = shared[int(value)]
                        values.append(value)
                    if values:
                        rows.append(values)
                if rows:
                    markdown = f"## Sheet {sheet_index}\n\n{_markdown_table(rows)}"
                    table_unit = make_unit(
                        source_ref,
                        "sheet",
                        "\n".join("\t".join(row) for row in rows),
                        index=sheet_index,
                        markdown=markdown,
                        structured_data={"rows": rows, "row_count": len(rows), "sheet": sheet_index},
                        location={"sheet": sheet_index},
                    )
                    units.append(table_unit)
    except Exception as exc:
        raise UnsupportedMediaError(f"Could not read XLSX structure: {exc}") from exc
    return units, {**metadata, "xlsx_sheets": len(units)}, warnings
