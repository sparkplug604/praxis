"""Freshness helpers for Reach evidence cards."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace

from .evidence import EvidenceCard
from .manifests import QueryManifest


def parse_instant(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def evidence_age_hours(card: EvidenceCard, *, now: datetime | None = None) -> float:
    current = now or datetime.now(timezone.utc)
    created = parse_instant(card.fresh_at)
    return (current - created).total_seconds() / 3600


def computed_freshness_status(card: EvidenceCard, manifest: QueryManifest, *, now: datetime | None = None) -> str:
    return "stale" if evidence_age_hours(card, now=now) > manifest.freshness_sla_hours else "fresh"


def with_computed_freshness(card: EvidenceCard, manifest: QueryManifest, *, now: datetime | None = None) -> EvidenceCard:
    return replace(card, freshness_status=computed_freshness_status(card, manifest, now=now))
