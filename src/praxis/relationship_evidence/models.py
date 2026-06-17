"""Typed models for relationship evidence APIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OntologyPredicate:
    id: str
    label: str
    aliases: tuple[str, ...] = ()
    subject_types: tuple[str, ...] = ()
    object_types: tuple[str, ...] = ()
    cardinality: str = "many"
    description: str = ""


@dataclass(frozen=True)
class RelationClaim:
    subject_text: str
    predicate: str
    object_value: str
    chunk_id: str
    confidence: float
    extractor: str
    subject_entity_id: str = ""
    object_entity_id: str = ""
    subject_type: str = "unknown"
    object_type: str = "unknown"
    evidence_annotation_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AcceptedEdge:
    id: str
    subject_text: str
    predicate: str
    object_value: str
    confidence: float
    status: str
    evidence_annotation_id: str = ""
    source_relation_candidate_id: str = ""
    chunk_id: str = ""
    subject_entity_id: str = ""
    object_entity_id: str = ""
    subject_type: str = "unknown"
    object_type: str = "unknown"
    ontology_id: str = ""
    ontology_version: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
