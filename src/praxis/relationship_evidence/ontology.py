"""Ontology loading and predicate normalization for relationship evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import OntologyPredicate


class Ontology:
    """Small schema object used to constrain relation candidates."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.id = str(payload.get("id") or "praxis.relationships")
        self.version = str(payload.get("version") or "")
        predicates = payload.get("predicates") or []
        self.predicates: dict[str, OntologyPredicate] = {}
        self.aliases: dict[str, str] = {}
        for item in predicates:
            predicate = OntologyPredicate(
                id=str(item["id"]),
                label=str(item.get("label") or item["id"]),
                aliases=tuple(str(alias).lower() for alias in item.get("aliases") or []),
                subject_types=tuple(str(value) for value in item.get("subject_types") or []),
                object_types=tuple(str(value) for value in item.get("object_types") or []),
                cardinality=str(item.get("cardinality") or "many"),
                description=str(item.get("description") or ""),
            )
            self.predicates[predicate.id] = predicate
            self.aliases[predicate.id.lower()] = predicate.id
            self.aliases[predicate.label.lower()] = predicate.id
            for alias in predicate.aliases:
                self.aliases[alias.lower()] = predicate.id

    def normalize_predicate(self, value: str) -> str:
        key = " ".join((value or "").strip().lower().replace("_", " ").split())
        if not key:
            return ""
        return self.aliases.get(key) or self.aliases.get(key.replace(" ", "_")) or key.replace(" ", "_")

    def predicate(self, value: str) -> OntologyPredicate | None:
        normalized = self.normalize_predicate(value)
        return self.predicates.get(normalized)

    def allows(self, predicate: str, subject_type: str, object_type: str) -> bool:
        spec = self.predicate(predicate)
        if spec is None:
            return False
        subject = subject_type or "unknown"
        obj = object_type or "unknown"
        subject_allowed = not spec.subject_types or subject in spec.subject_types or "unknown" in spec.subject_types
        object_allowed = not spec.object_types or obj in spec.object_types or "unknown" in spec.object_types
        return subject_allowed and object_allowed

    def cardinality(self, predicate: str) -> str:
        spec = self.predicate(predicate)
        return spec.cardinality if spec else "many"


def load_default_ontology() -> Ontology:
    path = Path(__file__).with_name("ontology.business.json")
    return Ontology(json.loads(path.read_text(encoding="utf-8")))
