# Relationship Evidence

Relationship Evidence is the Praxis Core workflow for turning chunk-level relationship claims into inspectable graph edges.

It sits between plain text retrieval and the SkillGraph. The goal is to avoid leaving every relationship trapped inside a chunk while also avoiding blind automatic graph mutation.

## What It Does

Relationship Evidence scans semantic chunks for relationship claims such as:

```text
Acme Corp acquired Northstar Analytics.
Acme Corp is led by Jamie Lee.
Beta Corp is based in Vancouver.
```

It can then:

- create relation candidates;
- attach evidence annotations to the source chunks;
- promote safe candidates into accepted graph edges;
- route suspicious candidates to review;
- query accepted relationships;
- compare two entities by their accepted relationships.

## Basic Flow

```bash
praxis relationship-evidence extract
praxis relationship-evidence promote
praxis relationship-evidence review list
praxis relationship-evidence query --subject "Acme" --predicate acquired
praxis relationship-evidence compare "Acme Corp" "Beta Corp"
```

## How It Relates To SkillGraph

SkillGraph stores Praxis knowledge objects and relationships such as sources, concepts, practices, risks, and reusable agent knowledge.

Relationship Evidence is more focused. It creates accepted relationship edges from source evidence after extraction and review.

| Layer | Role |
| --- | --- |
| SkillGraph | General Praxis graph for sources, concepts, practices, claims, risks, aliases, and reusable knowledge. |
| Relationship Evidence | Relationship-evidence layer for extracted business-style relations such as `acquired`, `led_by`, `customer_of`, `based_in`, and `uses`. |

Relationship Evidence does not replace the SkillGraph. It gives Praxis a stricter path for relationships that should be tied to evidence annotations and review rules.

## How It Relates To Entities

Entity-aware evidence detects and resolves mentions.

Relationship Evidence uses those entity foundations, but focuses on relationships between entities.

| Entity-Aware Evidence | Relationship Evidence |
| --- | --- |
| Finds mentions in chunks. | Finds relationships in chunks. |
| Resolves mentions to canonical SkillGraph nodes or text entity IDs. | Uses subject/object entity IDs when available. |
| Creates `ann:...` evidence annotations for mentions. | Creates `ann:...` evidence annotations for relation claims. |
| Helps retrieval find entity-related chunks. | Helps retrieval and inspection find accepted relationships. |

## How It Relates To Evidence Annotations

Every extracted relationship claim is backed by an evidence annotation.

That annotation stores:

- source chunk IDs;
- extracted subject, predicate, and object;
- matched text;
- confidence;
- extractor ID;
- ontology metadata;
- status such as `candidate`, `accepted`, or `needs_review`.

This matters because a graph edge should not be a naked assertion. It should point back to the text that caused it to exist.

## How It Relates To Conflicts

Relationship Evidence has its own review queue for relationship-candidate issues.

For example, a one-to-one predicate such as `led_by` should not silently accept two different leaders for the same organization. The promotion step accepts the first safe candidate and sends the conflicting candidate to review:

```bash
praxis relationship-evidence review list
praxis relationship-evidence review show "relationship-review:..."
praxis relationship-evidence review resolve "relationship-review:..." \
  --resolution "kept first leader pending source review"
```

The general conflict ledger still handles broader Praxis conflicts such as duplicate sources, duplicate entities, claim-like contradictions, and operational evidence disagreement. Relationship Evidence review items are narrower: they are relationship-promotion warnings.

## Built-In Ontology

The current built-in ontology is business-oriented and intentionally small.

It includes predicates such as:

- `acquired`
- `owned_by`
- `led_by`
- `customer_of`
- `supplier_of`
- `partners_with`
- `competitor_of`
- `based_in`
- `part_of`
- `uses`

Each predicate can define allowed subject/object types and cardinality. Cardinality is what lets Relationship Evidence route one-to-one relationship conflicts to review.

## Current Boundary

Relationship Evidence is rule-based today. It is useful for predictable relationship phrases, tests, demos, and early business-relationship extraction.

It is not yet a full production information-extraction system. It does not replace human review, authority anchors, governance checks, or domain-specific extraction models.

Use it as a safer bridge from text chunks toward structured relationships, not as an automatic truth engine.
