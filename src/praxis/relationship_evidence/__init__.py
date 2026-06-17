"""Built-in relationship evidence primitives for Praxis.

The relationship evidence package turns chunk-level evidence into inspectable
relationship candidates, accepted graph edges, and queryable relationship
context. Command wrappers may call this package, but the product behavior lives
here so UIs, agents, and API integrations can use the same code path.
"""

from .extraction import RelationExtractionSummary, RuleRelationExtractor, extract_relation_candidates
from .ontology import Ontology, load_default_ontology
from .promotion import PromotionSummary, promote_relation_candidates
from .query import compare_entity_relationships, find_relationships
from .review import get_review_item, list_review_items, resolve_review_item
from .service import RelationshipEvidenceService

__all__ = [
    "RelationshipEvidenceService",
    "Ontology",
    "PromotionSummary",
    "RelationExtractionSummary",
    "RuleRelationExtractor",
    "compare_entity_relationships",
    "extract_relation_candidates",
    "find_relationships",
    "get_review_item",
    "list_review_items",
    "load_default_ontology",
    "promote_relation_candidates",
    "resolve_review_item",
]
