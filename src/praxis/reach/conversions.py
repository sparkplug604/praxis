"""Client-specific conversion definition helpers for Praxis Reach."""

from __future__ import annotations

from typing import Any

from praxis.reach.models import ClientCapsule


def conversion_definitions(capsule: ClientCapsule, provider: str | None = None) -> list[dict[str, Any]]:
    """Return normalized conversion definitions from a client capsule.

    Definitions live in `metrics.json` under `conversion_definitions`. They are
    intentionally small and source-specific so agencies can map platform events
    to business meaning without treating all platform conversions as equal.
    """

    metric_root = capsule.metrics.get("conversion_definitions", [])
    raw_items = metric_root.values() if isinstance(metric_root, dict) else metric_root
    definitions: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source") or raw.get("provider") or "")
        if provider and source != provider:
            continue
        definition = {
            "id": str(raw.get("id") or raw.get("name") or raw.get("source_name") or ""),
            "source": source,
            "source_id": str(raw.get("source_id") or ""),
            "source_name": str(raw.get("source_name") or raw.get("event_name") or raw.get("name") or ""),
            "canonical_metric": str(raw.get("canonical_metric") or "conversions"),
            "weight": _number(raw.get("weight"), default=1.0),
            "primary": bool(raw.get("primary", True)),
            "description": str(raw.get("description") or ""),
        }
        if definition["source"] and (definition["source_id"] or definition["source_name"]):
            definitions.append(definition)
    return definitions


def conversion_match(value: str, definitions: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_value = normalize_conversion_name(value)
    for definition in definitions:
        source_id = normalize_conversion_name(str(definition.get("source_id") or ""))
        source_name = normalize_conversion_name(str(definition.get("source_name") or ""))
        if source_id and source_id == normalized_value:
            return definition
        if source_name and source_name == normalized_value:
            return definition
    return None


def normalize_conversion_name(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def describe_conversion_definitions(definitions: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for definition in definitions:
        source = definition.get("source")
        source_name = definition.get("source_name") or definition.get("source_id")
        canonical = definition.get("canonical_metric")
        out.append(f"{source}:{source_name}->{canonical}")
    return out


def _number(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
