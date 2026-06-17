"""Promote relation candidates into accepted Praxis graph edges."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ontology import Ontology, load_default_ontology
from .storage import (
    accepted_edge_conflict_exists,
    add_review_item,
    claim_from_candidate,
    connect_relationship_evidence_db,
    iter_relation_candidates,
    set_annotation_status,
    set_candidate_status,
    upsert_accepted_edge,
)


@dataclass(frozen=True)
class PromotionSummary:
    candidates_seen: int
    accepted: int
    needs_review: int
    rejected: int


def promotion_review_reason(claim, ontology: Ontology, min_confidence: float) -> str:
    if claim.confidence < min_confidence:
        return "confidence_below_threshold"
    if ontology.predicate(claim.predicate) is None:
        return "predicate_not_in_ontology"
    if not ontology.allows(claim.predicate, claim.subject_type, claim.object_type):
        return "entity_types_outside_ontology"
    return ""


def promote_relation_candidates(
    *,
    vector_db: Path,
    ontology: Ontology | None = None,
    status: str = "candidate",
    min_confidence: float = 0.70,
    limit: int = 0,
) -> PromotionSummary:
    ontology = ontology or load_default_ontology()
    candidates_seen = accepted = needs_review = rejected = 0
    with connect_relationship_evidence_db(vector_db) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO relationship_evidence_versions(id, ontology_id, ontology_version, metadata_json)
            VALUES (?, ?, ?, '{}')
            """,
            (f"{ontology.id}:{ontology.version}", ontology.id, ontology.version),
        )
        for row in iter_relation_candidates(connection, status=status, limit=limit):
            candidates_seen += 1
            candidate_id = str(row["id"])
            claim = claim_from_candidate(row)
            reason = promotion_review_reason(claim, ontology, min_confidence)
            if not reason and ontology.cardinality(claim.predicate) == "one" and accepted_edge_conflict_exists(connection, claim):
                reason = "cardinality_conflict"
            if reason:
                set_candidate_status(connection, candidate_id, "needs_review")
                set_annotation_status(connection, claim.evidence_annotation_id, "needs_review")
                add_review_item(
                    connection,
                    object_type="relation_candidate",
                    object_id=candidate_id,
                    reason=reason,
                    metadata={
                        "subject_text": claim.subject_text,
                        "predicate": claim.predicate,
                        "object_value": claim.object_value,
                        "confidence": claim.confidence,
                    },
                )
                needs_review += 1
                continue
            upsert_accepted_edge(
                connection,
                candidate_id=candidate_id,
                claim=claim,
                ontology_id=ontology.id,
                ontology_version=ontology.version,
            )
            set_candidate_status(connection, candidate_id, "accepted")
            set_annotation_status(connection, claim.evidence_annotation_id, "accepted")
            accepted += 1
    return PromotionSummary(
        candidates_seen=candidates_seen,
        accepted=accepted,
        needs_review=needs_review,
        rejected=rejected,
    )
