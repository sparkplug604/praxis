"""Entity resolution against canonical SkillGraph nodes and aliases."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import (
    GraphEntity,
    connect_entity_db,
    load_graph_entities,
    normalize_entity_text,
    record_resolution_decision,
    stable_id,
    upsert_candidate,
    upsert_evidence_annotation,
)


@dataclass(frozen=True)
class ResolutionSummary:
    mentions_seen: int
    accepted: int
    needs_review: int
    unresolved: int


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def candidate_matches(mention: Any, graph_entities: list[GraphEntity], *, fuzzy_threshold: float = 0.90) -> list[dict[str, Any]]:
    normalized = str(mention["normalized_text"] or "")
    metadata = json.loads(mention["metadata_json"] or "{}")
    matched_node_id = str(metadata.get("matched_node_id") or "")
    matches: list[dict[str, Any]] = []
    for entity in graph_entities:
        if matched_node_id and entity.node_id == matched_node_id:
            matches.append(
                {
                    "node_id": entity.node_id,
                    "candidate_name": entity.name,
                    "score": 0.99,
                    "method": "extractor_hint",
                    "rationale": {"matched_alias": entity.alias, "extractor_hint": matched_node_id},
                }
            )
            continue
        if normalized and normalized == entity.normalized_alias:
            matches.append(
                {
                    "node_id": entity.node_id,
                    "candidate_name": entity.name,
                    "score": 0.97,
                    "method": "exact_alias",
                    "rationale": {"matched_alias": entity.alias},
                }
            )
            continue
        score = similarity(normalized, entity.normalized_alias)
        if score >= fuzzy_threshold:
            matches.append(
                {
                    "node_id": entity.node_id,
                    "candidate_name": entity.name,
                    "score": score,
                    "method": "fuzzy_alias",
                    "rationale": {"matched_alias": entity.alias, "similarity": round(score, 4)},
                }
            )
    deduped: dict[str, dict[str, Any]] = {}
    for match in sorted(matches, key=lambda item: float(item["score"]), reverse=True):
        existing = deduped.get(str(match["node_id"]))
        if existing is None or float(match["score"]) > float(existing["score"]):
            deduped[str(match["node_id"])] = match
    return sorted(deduped.values(), key=lambda item: (-float(item["score"]), str(item["node_id"])))


def classify_resolution(matches: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None, str]:
    if not matches:
        return "unresolved", None, "no candidate matched canonical nodes or aliases"
    top = matches[0]
    if len(matches) == 1 and float(top["score"]) >= 0.95 and top["method"] in {"exact_alias", "extractor_hint"}:
        return "accepted", top, f"single high-confidence {top['method']} match"
    if len(matches) > 1 and float(top["score"]) >= 0.95:
        tied = [match for match in matches if float(match["score"]) >= 0.95]
        if len(tied) == 1 and float(top["score"]) - float(matches[1]["score"]) >= 0.10:
            return "accepted", top, "clear high-confidence winner"
    return "needs_review", top, "ambiguous or fuzzy entity resolution"


def ensure_annotation_for_accepted_mention(connection, mention: Any, match: dict[str, Any], rationale: str) -> str:
    node_id = str(match["node_id"])
    annotation_id = upsert_evidence_annotation(
        connection,
        annotation_type="entity_mention",
        chunk_ids=[str(mention["chunk_id"])],
        entity_ids=[node_id],
        extracted={
            "mention_id": str(mention["id"]),
            "surface_text": str(mention["surface_text"]),
            "normalized_text": str(mention["normalized_text"]),
            "entity_type": str(mention["entity_type"]),
            "start_offset": int(mention["start_offset"]),
            "end_offset": int(mention["end_offset"]),
            "resolution_rationale": rationale,
        },
        confidence=min(float(mention["confidence"] or 0.0), float(match["score"])),
        status="accepted",
        extractor=str(mention["extractor"]),
        governance={
            "entity_resolution_status": "accepted",
            "entity_resolution_confidence": float(match["score"]),
            "entity_resolution_method": str(match["method"]),
            "resolved_entity_ids": [node_id],
            "source_chunk_ids": [str(mention["chunk_id"])],
        },
    )
    connection.execute(
        """
        UPDATE entity_mentions
        SET status = 'accepted',
            resolution_status = 'accepted',
            resolved_node_id = ?,
            evidence_annotation_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (node_id, annotation_id, str(mention["id"])),
    )
    return annotation_id


def resolve_mentions(
    *,
    vector_db: Path,
    kg_db: Path,
    status: str = "candidate",
    limit: int = 0,
) -> ResolutionSummary:
    graph_entities = load_graph_entities(kg_db)
    mentions_seen = accepted = needs_review = unresolved = 0
    with connect_entity_db(vector_db) as connection:
        params: list[Any] = []
        status_clause = ""
        if status:
            status_clause = "WHERE em.status = ? OR em.resolution_status = ?"
            params.extend([status, "unresolved" if status == "candidate" else status])
        limit_clause = ""
        if limit:
            limit_clause = "LIMIT ?"
            params.append(limit)
        mentions = connection.execute(
            f"""
            SELECT em.*
            FROM entity_mentions em
            {status_clause}
            ORDER BY em.created_at, em.id
            {limit_clause}
            """,
            params,
        ).fetchall()
        for mention in mentions:
            mentions_seen += 1
            matches = candidate_matches(mention, graph_entities)
            resolution_status, top, rationale = classify_resolution(matches)
            candidate_ids: list[str] = []
            for match in matches:
                candidate_status = "accepted" if top and match["node_id"] == top["node_id"] and resolution_status == "accepted" else "candidate"
                if resolution_status == "needs_review":
                    candidate_status = "needs_review"
                candidate_ids.append(
                    upsert_candidate(
                        connection,
                        mention_id=str(mention["id"]),
                        node_id=str(match["node_id"]),
                        candidate_name=str(match["candidate_name"]),
                        score=float(match["score"]),
                        method=str(match["method"]),
                        status=candidate_status,
                        rationale=dict(match["rationale"]),
                    )
                )
            if resolution_status == "accepted" and top:
                annotation_id = ensure_annotation_for_accepted_mention(connection, mention, top, rationale)
                record_resolution_decision(
                    connection,
                    mention_id=str(mention["id"]),
                    candidate_id=candidate_ids[0] if candidate_ids else "",
                    node_id=str(top["node_id"]),
                    decision="accepted",
                    rationale=rationale,
                )
                accepted += 1
            elif resolution_status == "needs_review":
                connection.execute(
                    """
                    UPDATE entity_mentions
                    SET resolution_status = 'needs_review',
                        status = 'needs_review',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (str(mention["id"]),),
                )
                needs_review += 1
            else:
                connection.execute(
                    "UPDATE entity_mentions SET resolution_status = 'unresolved', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (str(mention["id"]),),
                )
                unresolved += 1
    return ResolutionSummary(mentions_seen=mentions_seen, accepted=accepted, needs_review=needs_review, unresolved=unresolved)


def annotation_source_ref(annotation_id: str) -> str:
    return stable_id("entity-annotation-ref", [annotation_id])
