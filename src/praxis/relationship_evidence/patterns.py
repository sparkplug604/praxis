"""Declarative relation pattern specs for the built-in rule extractor."""

from __future__ import annotations

import re
from dataclasses import dataclass


ENTITY_TOKEN = r"[A-Z][A-Za-z0-9&'-]*"
ENTITY_PATTERN = rf"{ENTITY_TOKEN}(?:\s+(?:{ENTITY_TOKEN}|and|of|the)){{0,5}}"


@dataclass(frozen=True)
class RelationPatternSpec:
    predicate: str
    verb_aliases: tuple[str, ...]
    template: str
    confidence: float = 0.82


@dataclass(frozen=True)
class CompiledRelationPattern:
    spec: RelationPatternSpec
    pattern: re.Pattern[str]


def _verb_group(aliases: tuple[str, ...]) -> str:
    return "|".join(re.escape(alias) for alias in aliases)


def compile_relation_pattern(spec: RelationPatternSpec) -> CompiledRelationPattern:
    subject = rf"(?P<subject>{ENTITY_PATTERN})"
    verb = rf"(?P<verb>{_verb_group(spec.verb_aliases)})"
    obj = rf"(?P<object>{ENTITY_PATTERN})"
    pattern_text = spec.template.format(subject=subject, verb=verb, object=obj)
    return CompiledRelationPattern(spec=spec, pattern=re.compile(rf"\b{pattern_text}\b"))


def compile_relation_patterns(specs: tuple[RelationPatternSpec, ...]) -> tuple[CompiledRelationPattern, ...]:
    return tuple(compile_relation_pattern(spec) for spec in specs)


DEFAULT_RELATION_PATTERN_SPECS: tuple[RelationPatternSpec, ...] = (
    RelationPatternSpec(
        predicate="acquired",
        verb_aliases=("acquired", "bought", "purchased"),
        template="{subject}\\s+{verb}\\s+{object}",
    ),
    RelationPatternSpec(
        predicate="owned_by",
        verb_aliases=("owned by", "controlled by"),
        template="{subject}\\s+(?:is|was|are|were)\\s+{verb}\\s+{object}",
    ),
    RelationPatternSpec(
        predicate="led_by",
        verb_aliases=("led by", "headed by", "run by"),
        template="{subject}\\s+(?:is|was|are|were)\\s+{verb}\\s+{object}",
    ),
    RelationPatternSpec(
        predicate="customer_of",
        verb_aliases=("customer of", "client of"),
        template="{subject}\\s+(?:is|was|are|were)\\s+(?:a\\s+)?{verb}\\s+{object}",
    ),
    RelationPatternSpec(
        predicate="supplier_of",
        verb_aliases=("supplier of", "vendor for"),
        template="{subject}\\s+(?:is|was|are|were)\\s+(?:a\\s+)?{verb}\\s+{object}",
    ),
    RelationPatternSpec(
        predicate="partners_with",
        verb_aliases=("partners with", "partnered with"),
        template="{subject}\\s+{verb}\\s+{object}",
    ),
    RelationPatternSpec(
        predicate="competitor_of",
        verb_aliases=("competes with",),
        template="{subject}\\s+{verb}\\s+{object}",
    ),
    RelationPatternSpec(
        predicate="based_in",
        verb_aliases=("based in", "located in", "headquartered in"),
        template="{subject}\\s+(?:is|was|are|were)\\s+{verb}\\s+{object}",
    ),
    RelationPatternSpec(
        predicate="part_of",
        verb_aliases=("part of", "division of", "subsidiary of"),
        template="{subject}\\s+(?:is|was|are|were)\\s+{verb}\\s+{object}",
    ),
    RelationPatternSpec(
        predicate="uses",
        verb_aliases=("uses", "runs on", "standardized on"),
        template="{subject}\\s+{verb}\\s+{object}",
    ),
)


DEFAULT_RELATION_PATTERNS = compile_relation_patterns(DEFAULT_RELATION_PATTERN_SPECS)
