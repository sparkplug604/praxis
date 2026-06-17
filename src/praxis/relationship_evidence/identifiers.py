"""Stable identifiers and normalized keys for relationship evidence."""

from __future__ import annotations

from praxis.entities.storage import normalize_entity_text, stable_id


def text_entity_id(surface_text: str, entity_type: str = "unknown") -> str:
    return stable_id("text-entity", [entity_type or "unknown", normalize_entity_text(surface_text)])


def relation_key(subject_text: str, predicate: str, object_value: str) -> str:
    return "|".join(
        [
            normalize_entity_text(subject_text),
            (predicate or "").strip().lower(),
            normalize_entity_text(object_value),
        ]
    )
