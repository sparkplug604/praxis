"""Deterministic entity mention extraction for Praxis chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import (
    GraphEntity,
    connect_entity_db,
    iter_chunks,
    load_graph_entities,
    mention_payload,
    normalize_entity_text,
    stable_id,
    upsert_mention,
)


@dataclass(frozen=True)
class ExtractionSummary:
    run_id: str
    chunks_scanned: int
    mentions_written: int
    extractor: str


def alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias.strip())
    return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.IGNORECASE)


def candidate_capitalized_mentions(text: str) -> list[tuple[str, int, int]]:
    pattern = re.compile(r"\b(?:[A-Z][A-Za-z0-9&'.-]+(?:\s+|$)){2,5}")
    mentions: list[tuple[str, int, int]] = []
    for match in pattern.finditer(text):
        surface = match.group(0).strip()
        if len(surface) < 4:
            continue
        if len(surface.split()) > 6:
            continue
        mentions.append((surface, match.start(), match.start() + len(surface)))
    return mentions


def extract_known_entity_mentions(
    text: str,
    entities: list[GraphEntity],
    *,
    min_alias_len: int = 3,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for entity in sorted(entities, key=lambda item: len(item.alias), reverse=True):
        alias = entity.alias.strip()
        if len(normalize_entity_text(alias)) < min_alias_len:
            continue
        for match in alias_pattern(alias).finditer(text):
            key = (entity.node_id, match.start(), match.end())
            if key in seen:
                continue
            seen.add(key)
            hits.append(
                {
                    "surface_text": match.group(0),
                    "entity_type": entity.entity_type,
                    "start_offset": match.start(),
                    "end_offset": match.end(),
                    "confidence": 0.96 if entity.source == "alias" else 0.92,
                    "metadata": {
                        "matched_node_id": entity.node_id,
                        "matched_name": entity.name,
                        "matched_alias": entity.alias,
                        "match_source": entity.source,
                    },
                }
            )
    return sorted(hits, key=lambda item: (item["start_offset"], -item["confidence"]))


def extract_pattern_mentions(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for surface, start, end in candidate_capitalized_mentions(text):
        hits.append(
            {
                "surface_text": surface,
                "entity_type": "candidate",
                "start_offset": start,
                "end_offset": end,
                "confidence": 0.45,
                "metadata": {"match_source": "capitalized_phrase"},
            }
        )
    return hits


def extract_mentions(
    *,
    vector_db: Path,
    kg_db: Path,
    changed_only: bool = False,
    include_patterns: bool = False,
    limit: int = 0,
) -> ExtractionSummary:
    extractor = "rule_aliases+patterns" if include_patterns else "rule_aliases"
    run_id = stable_id("entity-run", [extractor, str(vector_db), str(kg_db)])
    entities = load_graph_entities(kg_db)
    chunks_scanned = 0
    mentions_written = 0
    with connect_entity_db(vector_db) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO entity_extraction_runs(id, scope, extractor, status, started_at, metadata_json)
            VALUES (?, 'semantic_chunks', ?, 'running', CURRENT_TIMESTAMP, ?)
            """,
            (run_id, extractor, "{}"),
        )
        for chunk in iter_chunks(connection, changed_only=changed_only, limit=limit):
            chunks_scanned += 1
            text = str(chunk["text"] or "")
            hits = extract_known_entity_mentions(text, entities)
            if include_patterns:
                hits.extend(extract_pattern_mentions(text))
            # Avoid duplicate surfaces at the same span. Prefer the higher-confidence known-entity hit.
            deduped: dict[tuple[int, int, str], dict[str, Any]] = {}
            for hit in hits:
                key = (
                    int(hit["start_offset"]),
                    int(hit["end_offset"]),
                    normalize_entity_text(str(hit["surface_text"])),
                )
                current = deduped.get(key)
                if current is None or float(hit["confidence"]) > float(current["confidence"]):
                    deduped[key] = hit
            for hit in deduped.values():
                payload = mention_payload(
                    chunk=chunk,
                    surface_text=str(hit["surface_text"]),
                    entity_type=str(hit["entity_type"]),
                    start_offset=int(hit["start_offset"]),
                    end_offset=int(hit["end_offset"]),
                    extractor=extractor,
                    confidence=float(hit["confidence"]),
                    metadata=dict(hit.get("metadata") or {}),
                )
                upsert_mention(connection, payload)
                mentions_written += 1
        connection.execute(
            """
            UPDATE entity_extraction_runs
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP, metadata_json = ?
            WHERE id = ?
            """,
            (f'{{"chunks_scanned":{chunks_scanned},"mentions_written":{mentions_written}}}', run_id),
        )
    return ExtractionSummary(run_id=run_id, chunks_scanned=chunks_scanned, mentions_written=mentions_written, extractor=extractor)
