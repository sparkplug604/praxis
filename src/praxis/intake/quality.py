"""Parse-quality scoring for Praxis intake."""

from __future__ import annotations

from .models import ExtractedUnit, ParseQuality


def score_parse_quality(
    *,
    media_type: str,
    units: list[ExtractedUnit],
    warnings: list[str],
    metadata: dict,
) -> ParseQuality:
    text_chars = sum(len(unit.display_text()) for unit in units)
    unit_count = len(units)
    structured_units = sum(1 for unit in units if unit.structured_data)
    empty_units = sum(1 for unit in units if not unit.display_text())

    reasons: list[str] = []
    quality_warnings = list(warnings)

    if text_chars <= 0:
        quality_warnings.append("no_searchable_text_extracted")
        return ParseQuality(score=0.0, reasons=["text_chars:0"], warnings=quality_warnings)

    score = 0.35
    density_score = min(0.35, text_chars / 6000.0)
    score += density_score
    reasons.append(f"text_chars:{text_chars}")

    if unit_count:
        score += min(0.12, unit_count / 80.0)
        reasons.append(f"units:{unit_count}")

    if structured_units:
        score += min(0.12, structured_units / 40.0)
        reasons.append(f"structured_units:{structured_units}")

    if empty_units:
        penalty = min(0.15, empty_units / max(unit_count, 1) * 0.15)
        score -= penalty
        reasons.append(f"empty_unit_penalty:{penalty:.3f}")

    if media_type == "application/pdf":
        pages = int(metadata.get("pdf_pages") or 0)
        page_units = sum(1 for unit in units if unit.unit_type == "page")
        if pages and page_units < pages:
            quality_warnings.append(f"pdf_empty_or_unreadable_pages:{pages - page_units}")
            score -= min(0.2, (pages - page_units) / max(pages, 1) * 0.2)

    if media_type.startswith(("audio/", "video/")):
        transcript_units = sum(1 for unit in units if "transcript" in unit.unit_type)
        if transcript_units:
            reasons.append(f"transcript_units:{transcript_units}")
            score += min(0.1, transcript_units / 100.0)
        else:
            quality_warnings.append("media_has_no_transcript_units")
            reasons.append("media_metadata_only")
            score = min(score, 0.35)

    if warnings:
        score -= min(0.25, len(warnings) * 0.05)
        reasons.append(f"warning_penalty:{len(warnings)}")

    return ParseQuality(score=max(0.0, min(1.0, score)), reasons=reasons, warnings=quality_warnings)
