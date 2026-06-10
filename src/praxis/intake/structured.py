"""Structured text converters for Praxis intake."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from .models import ExtractedUnit
from .text import decode_text
from .units import make_unit


def _markdown_table(rows: list[list[str]], *, limit: int = 40) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows[:limit]]
    header = normalized[0]
    body = normalized[1:]
    lines = [
        "| " + " | ".join(cell.replace("\n", " ").strip() for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(cell.replace("\n", " ").strip() for cell in row) + " |")
    return "\n".join(lines)


def convert_csv(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    text = decode_text(body)
    rows = list(csv.reader(io.StringIO(text)))
    warnings: list[str] = []
    units: list[ExtractedUnit] = []
    if not rows:
        return [], metadata, ["csv_empty"]
    table_markdown = _markdown_table(rows)
    table_unit = make_unit(
        source_ref,
        "table",
        "\n".join(",".join(cell for cell in row) for row in rows),
        markdown=table_markdown,
        structured_data={"rows": rows, "row_count": len(rows)},
        location={"source": source_ref},
    )
    units.append(table_unit)
    header = rows[0]
    for index, row in enumerate(rows[1:], 1):
        values = {header[i] if i < len(header) else f"column_{i + 1}": value for i, value in enumerate(row)}
        row_text = "; ".join(f"{key}: {value}" for key, value in values.items())
        units.append(
            make_unit(
                source_ref,
                "table_row",
                row_text,
                index=index,
                structured_data={"row": values},
                location={"row": index + 1},
                parent_unit_id=table_unit.unit_id,
            )
        )
    metadata = {**metadata, "csv_rows": len(rows), "csv_columns": len(header)}
    if len(rows) > 5000:
        warnings.append("large_csv_extracted; consider structured warehouse ingestion for production use")
    return units, metadata, warnings


def convert_json(source_ref: str, body: bytes, metadata: dict[str, Any]) -> tuple[list[ExtractedUnit], dict[str, Any], list[str]]:
    text = decode_text(body)
    warnings: list[str] = []
    try:
        if source_ref.lower().endswith(".jsonl"):
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
            pretty = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records)
            structured = {"records": records, "record_count": len(records)}
            unit_type = "jsonl_records"
        else:
            parsed = json.loads(text)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False, sort_keys=True)
            structured = {"json": parsed}
            unit_type = "json_document"
    except json.JSONDecodeError as exc:
        warnings.append(f"json_parse_error:{exc.lineno}:{exc.colno}")
        return [make_unit(source_ref, "document", text, confidence="low", warnings=warnings)], metadata, warnings
    return [make_unit(source_ref, unit_type, pretty, structured_data=structured, location={"source": source_ref})], metadata, warnings
