"""Convert Reach evidence cards into local source files for Praxis Core capture."""

from __future__ import annotations

from pathlib import Path

from .evidence import EvidenceCard
from .storage import reach_dir, slug, write_text_atomic


def evidence_source_path(root: Path, card: EvidenceCard) -> Path:
    return reach_dir(root) / "evidence_sources" / f"{slug(card.evidence_id.replace(':', '-'))}.md"


def render_evidence_source(card: EvidenceCard) -> str:
    metrics = "\n".join(
        f"- {key}: {value}" + (f" (source: {card.metric_sources[key]})" if key in card.metric_sources else "")
        for key, value in sorted(card.metrics.items())
    ) or "- No metrics captured."
    warnings = "\n".join(f"- {warning}" for warning in card.warnings) or "- No warnings."
    conflicts = "\n".join(f"- {conflict}" for conflict in card.conflicts) or "- No conflicts recorded."
    links = "\n".join(f"- {link}" for link in card.source_links) or "- No source links."
    return "\n".join(
        [
            f"# Reach Evidence: {card.query_id} / {card.client_id}",
            "",
            f"- evidence_id: `{card.evidence_id}`",
            f"- client_id: `{card.client_id}`",
            f"- query_id: `{card.query_id}`",
            f"- fresh_at: `{card.fresh_at}`",
            f"- freshness_status: `{card.freshness_status}`",
            f"- data_quality_status: `{card.data_quality_status}`",
            f"- confidence_score: `{card.confidence_score:.2f}`",
            f"- partial_data: `{card.partial_data}`",
            f"- storage_level: `{card.storage_level}`",
            f"- redaction_status: `{card.redaction_status}`",
            "",
            "## Summary",
            "",
            card.summary,
            "",
            "## Metrics",
            "",
            metrics,
            "",
            "## Warnings",
            "",
            warnings,
            "",
            "## Conflicts",
            "",
            conflicts,
            "",
            "## Source Links",
            "",
            links,
            "",
        ]
    )


def write_evidence_source(root: Path, card: EvidenceCard) -> Path:
    path = evidence_source_path(root, card)
    write_text_atomic(path, render_evidence_source(card))
    return path
