"""Context pack templates for Reach evidence."""

from __future__ import annotations

from .evidence import EvidenceCard


def render_template(card: EvidenceCard, template: str) -> str:
    if template == "reach_drop_diagnosis":
        return render_reach_drop(card)
    if template == "weekly_gtm_review":
        return render_weekly_review(card)
    if template == "pipeline_health_check":
        return render_pipeline_health(card)
    return render_generic(card, template)


def render_generic(card: EvidenceCard, template: str) -> str:
    return "\n".join(_common_header(card, template) + _summary_sections(card))


def render_weekly_review(card: EvidenceCard) -> str:
    return "\n".join(
        _common_header(card, "Weekly GTM Review")
        + [
            "## Operating Readout",
            "",
            card.summary,
            "",
            "## Metrics To Review",
            "",
            _metrics(card),
            "",
            "## Agent Guidance",
            "",
            "- Treat CRM metrics as source-of-truth for pipeline unless the client capsule says otherwise.",
            "- Treat ad-platform conversion metrics as directional until confirmed by CRM.",
            "- If warnings are present, mention them before making budget recommendations.",
            "",
        ]
        + _warning_and_link_sections(card)
    )


def render_reach_drop(card: EvidenceCard) -> str:
    return "\n".join(
        _common_header(card, "Reach Drop Diagnosis")
        + [
            "## Diagnosis Starting Point",
            "",
            card.summary,
            "",
            "## Check First",
            "",
            "- Spend trend versus reach trend.",
            "- Frequency or audience saturation if available.",
            "- CTR and CPC movement.",
            "- CRM-confirmed lead and opportunity movement.",
            "- Attribution mismatch warnings.",
            "",
            "## Metrics",
            "",
            _metrics(card),
            "",
        ]
        + _warning_and_link_sections(card)
    )


def render_pipeline_health(card: EvidenceCard) -> str:
    return "\n".join(
        _common_header(card, "Pipeline Health Check")
        + [
            "## Pipeline Readout",
            "",
            card.summary,
            "",
            "## Metrics",
            "",
            _metrics(card),
            "",
            "## Agent Guidance",
            "",
            "- Compare lead volume with opportunity creation before blaming traffic.",
            "- Call out stale CRM evidence before making revenue claims.",
            "- Separate pipeline amount from closed-won revenue.",
            "",
        ]
        + _warning_and_link_sections(card)
    )


def _common_header(card: EvidenceCard, title: str) -> list[str]:
    return [
        f"# {title}",
        "",
        f"- client_id: `{card.client_id}`",
        f"- evidence_id: `{card.evidence_id}`",
        f"- query_id: `{card.query_id}`",
        f"- manifest_version: `{card.manifest_version}`",
        f"- fresh_at: `{card.fresh_at}`",
        f"- freshness_status: `{card.freshness_status}`",
        f"- data_quality_status: `{card.data_quality_status}`",
        f"- confidence_score: `{card.confidence_score:.2f}`",
        f"- partial_data: `{card.partial_data}`",
        f"- storage_level: `{card.storage_level}`",
        f"- redaction_status: `{card.redaction_status}`",
        "",
    ]


def _summary_sections(card: EvidenceCard) -> list[str]:
    return [
        "## Summary",
        "",
        card.summary,
        "",
        "## Metrics",
        "",
        _metrics(card),
        "",
    ] + _warning_and_link_sections(card)


def _warning_and_link_sections(card: EvidenceCard) -> list[str]:
    return [
        "## Warnings",
        "",
        _warnings(card),
        "",
        "## Conflicts",
        "",
        _conflicts(card),
        "",
        "## Source Links",
        "",
        _links(card),
        "",
    ]


def _metrics(card: EvidenceCard) -> str:
    lines = []
    for key, value in sorted(card.metrics.items()):
        source = card.metric_sources.get(key)
        suffix = f" (source: {source})" if source else ""
        lines.append(f"- {key}: {value}{suffix}")
    return "\n".join(lines) or "- No metrics captured."


def _warnings(card: EvidenceCard) -> str:
    return "\n".join(f"- {warning}" for warning in card.warnings) or "- No warnings."


def _conflicts(card: EvidenceCard) -> str:
    if card.conflict_records:
        return "\n".join(
            f"- {record.get('severity', 'unknown')} {record.get('conflict_type', 'conflict')}: {record.get('message', '')}"
            for record in card.conflict_records
        )
    return "\n".join(f"- {conflict}" for conflict in card.conflicts) or "- No conflicts recorded."


def _links(card: EvidenceCard) -> str:
    return "\n".join(f"- {link}" for link in card.source_links) or "- No source links."
