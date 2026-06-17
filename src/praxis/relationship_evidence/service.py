"""Product-facing service boundary for Praxis relationship evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .extraction import RelationExtractionSummary, RelationExtractor, extract_relation_candidates
from .ontology import Ontology, load_default_ontology
from .promotion import PromotionSummary, promote_relation_candidates
from .query import compare_entity_relationships, find_relationships
from .review import get_review_item, list_review_items, resolve_review_item


@dataclass(frozen=True)
class RelationshipEvidenceService:
    """Coordinate relationship evidence without exposing storage details to callers."""

    vector_db: Path
    ontology: Ontology | None = None
    relation_extractor: RelationExtractor | None = None

    def active_ontology(self) -> Ontology:
        return self.ontology or load_default_ontology()

    def extract_relations(
        self,
        *,
        changed_only: bool = False,
        limit: int = 0,
    ) -> RelationExtractionSummary:
        ontology = self.active_ontology()
        return extract_relation_candidates(
            vector_db=self.vector_db,
            ontology=ontology,
            changed_only=changed_only,
            limit=limit,
            relation_extractor=self.relation_extractor,
        )

    def promote_candidates(
        self,
        *,
        status: str = "candidate",
        min_confidence: float = 0.70,
        limit: int = 0,
    ) -> PromotionSummary:
        return promote_relation_candidates(
            vector_db=self.vector_db,
            ontology=self.active_ontology(),
            status=status,
            min_confidence=min_confidence,
            limit=limit,
        )

    def find_relationships(
        self,
        *,
        subject: str = "",
        predicate: str = "",
        object_value: str = "",
        query: str = "",
        status: str = "accepted",
        limit: int = 20,
        include_evidence: bool = True,
    ) -> list[dict[str, Any]]:
        return find_relationships(
            vector_db=self.vector_db,
            subject=subject,
            predicate=predicate,
            object_value=object_value,
            query=query,
            status=status,
            limit=limit,
            include_evidence=include_evidence,
        )

    def compare_entities(self, left: str, right: str, *, limit: int = 50) -> dict[str, Any]:
        return compare_entity_relationships(vector_db=self.vector_db, left=left, right=right, limit=limit)

    def list_review_items(self, *, status: str = "open", limit: int = 25) -> list[dict[str, Any]]:
        return list_review_items(vector_db=self.vector_db, status=status, limit=limit)

    def get_review_item(self, review_id: str) -> dict[str, Any] | None:
        return get_review_item(vector_db=self.vector_db, review_id=review_id)

    def resolve_review_item(
        self,
        review_id: str,
        *,
        status: str,
        resolution: str = "",
        notes: str = "",
    ) -> bool:
        return resolve_review_item(
            vector_db=self.vector_db,
            review_id=review_id,
            status=status,
            resolution=resolution,
            notes=notes,
        )
