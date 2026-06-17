"""Relation candidate extraction from Praxis semantic chunks."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from praxis.entities.storage import iter_chunks, upsert_evidence_annotation

from .models import RelationClaim
from .ontology import Ontology, load_default_ontology
from .patterns import DEFAULT_RELATION_PATTERNS, CompiledRelationPattern
from .storage import connect_relationship_evidence_db, upsert_relation_candidate


DEFAULT_EXTRACTOR = "praxis.rule_relation_extractor.v1"


@dataclass(frozen=True)
class RelationExtractionSummary:
    chunks_scanned: int
    claims_seen: int
    candidates_written: int
    extractor: str


RELATION_PATTERNS = DEFAULT_RELATION_PATTERNS


ORG_HINTS = {
    "agency",
    "analytics",
    "bank",
    "clinic",
    "co",
    "company",
    "corp",
    "corporation",
    "group",
    "hospital",
    "inc",
    "labs",
    "llc",
    "ltd",
    "systems",
    "technologies",
    "university",
}
LOCATION_HINTS = {
    "atlanta",
    "austin",
    "boston",
    "chicago",
    "dallas",
    "denver",
    "london",
    "new york",
    "paris",
    "san francisco",
    "seattle",
    "toronto",
    "vancouver",
}
PRODUCT_HINTS = {"platform", "suite", "cloud", "crm", "erp", "database", "warehouse", "app"}


class RelationExtractor(Protocol):
    extractor_id: str

    def extract_claims(self, text: str, *, chunk_id: str) -> list[RelationClaim]:
        ...


def clean_entity_text(value: str) -> str:
    cleaned = " ".join((value or "").split())
    return cleaned.strip(" ,.;:()[]{}\"'")


def guess_entity_type(value: str, *, predicate: str = "", role: str = "") -> str:
    text = clean_entity_text(value)
    lowered = text.lower()
    tokens = lowered.replace(".", "").split()
    if lowered in LOCATION_HINTS:
        return "location"
    if any(token in ORG_HINTS for token in tokens):
        return "organization"
    if any(token in PRODUCT_HINTS for token in tokens):
        return "product"
    if predicate in {"acquired", "owned_by", "customer_of", "supplier_of", "partners_with", "competitor_of", "part_of"}:
        return "organization"
    if predicate == "based_in" and role == "object":
        return "location"
    if len(tokens) == 2 and all(token[:1].isalpha() for token in tokens):
        return "person"
    return "unknown"


@dataclass(frozen=True)
class RuleRelationExtractor:
    ontology: Ontology
    extractor_id: str = DEFAULT_EXTRACTOR
    patterns: tuple[CompiledRelationPattern, ...] = DEFAULT_RELATION_PATTERNS

    def extract_claims(self, text: str, *, chunk_id: str) -> list[RelationClaim]:
        claims: list[RelationClaim] = []
        seen: set[tuple[str, str, str, int]] = set()
        for compiled in self.patterns:
            for match in compiled.pattern.finditer(text or ""):
                subject = clean_entity_text(match.group("subject"))
                obj = clean_entity_text(match.group("object"))
                if not subject or not obj:
                    continue
                predicate = self.ontology.normalize_predicate(compiled.spec.predicate)
                key = (subject.lower(), predicate, obj.lower(), match.start())
                if key in seen:
                    continue
                seen.add(key)
                subject_type = guess_entity_type(subject, predicate=predicate, role="subject")
                object_type = guess_entity_type(obj, predicate=predicate, role="object")
                claims.append(
                    RelationClaim(
                        subject_text=subject,
                        predicate=predicate,
                        object_value=obj,
                        chunk_id=chunk_id,
                        confidence=compiled.spec.confidence,
                        extractor=self.extractor_id,
                        subject_type=subject_type,
                        object_type=object_type,
                        metadata={
                            "match_span": [match.start(), match.end()],
                            "matched_text": match.group(0),
                            "matched_verb": match.groupdict().get("verb", ""),
                            "pattern_predicate": compiled.spec.predicate,
                        },
                    )
                )
        return claims


def extract_claims_from_text(
    text: str,
    *,
    chunk_id: str,
    ontology: Ontology | None = None,
    extractor: str = DEFAULT_EXTRACTOR,
) -> list[RelationClaim]:
    ontology = ontology or load_default_ontology()
    return RuleRelationExtractor(ontology=ontology, extractor_id=extractor).extract_claims(text, chunk_id=chunk_id)


def extract_relation_candidates(
    *,
    vector_db: Path,
    ontology: Ontology | None = None,
    changed_only: bool = False,
    limit: int = 0,
    extractor: str = DEFAULT_EXTRACTOR,
    relation_extractor: RelationExtractor | None = None,
) -> RelationExtractionSummary:
    ontology = ontology or load_default_ontology()
    relation_extractor = relation_extractor or RuleRelationExtractor(ontology=ontology, extractor_id=extractor)
    chunks_scanned = 0
    claims_seen = 0
    candidates_written = 0
    with connect_relationship_evidence_db(vector_db) as connection:
        for chunk in iter_chunks(connection, changed_only=changed_only, limit=limit):
            chunks_scanned += 1
            claims = relation_extractor.extract_claims(str(chunk["text"] or ""), chunk_id=str(chunk["id"]))
            claims_seen += len(claims)
            for claim in claims:
                annotation_id = upsert_evidence_annotation(
                    connection,
                    annotation_type="relation_claim",
                    chunk_ids=[claim.chunk_id],
                    entity_ids=[claim.subject_entity_id, claim.object_entity_id],
                    extracted={
                        "subject_text": claim.subject_text,
                        "subject_type": claim.subject_type,
                        "predicate": claim.predicate,
                        "object_value": claim.object_value,
                        "object_type": claim.object_type,
                        "matched_text": claim.metadata.get("matched_text", ""),
                        "match_span": claim.metadata.get("match_span", []),
                    },
                    confidence=claim.confidence,
                    status="candidate",
                    extractor=extractor,
                    governance={
                        "ontology_id": ontology.id,
                        "ontology_version": ontology.version,
                        "source_chunk_ids": [claim.chunk_id],
                    },
                )
                upsert_relation_candidate(connection, replace(claim, evidence_annotation_id=annotation_id))
                candidates_written += 1
    return RelationExtractionSummary(
        chunks_scanned=chunks_scanned,
        claims_seen=claims_seen,
        candidates_written=candidates_written,
        extractor=relation_extractor.extractor_id,
    )
