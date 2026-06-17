"""SQLite schema extensions for Praxis relationship evidence."""

from __future__ import annotations

import sqlite3

from praxis.entities.storage import ensure_entity_schema


def ensure_relationship_evidence_schema(connection: sqlite3.Connection) -> None:
    ensure_entity_schema(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS relationship_evidence_versions (
          id TEXT PRIMARY KEY,
          ontology_id TEXT NOT NULL DEFAULT '',
          ontology_version TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'active',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS accepted_graph_edges (
          id TEXT PRIMARY KEY,
          subject_entity_id TEXT NOT NULL DEFAULT '',
          subject_text TEXT NOT NULL DEFAULT '',
          subject_type TEXT NOT NULL DEFAULT 'unknown',
          predicate TEXT NOT NULL,
          object_entity_id TEXT NOT NULL DEFAULT '',
          object_value TEXT NOT NULL DEFAULT '',
          object_type TEXT NOT NULL DEFAULT 'unknown',
          confidence REAL NOT NULL DEFAULT 0.0,
          status TEXT NOT NULL DEFAULT 'accepted',
          ontology_id TEXT NOT NULL DEFAULT '',
          ontology_version TEXT NOT NULL DEFAULT '',
          source_relation_candidate_id TEXT NOT NULL DEFAULT '',
          evidence_annotation_id TEXT NOT NULL DEFAULT '',
          chunk_id TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(subject_entity_id, predicate, object_entity_id, object_value, source_relation_candidate_id)
        );

        CREATE TABLE IF NOT EXISTS accepted_graph_edge_evidence (
          edge_id TEXT NOT NULL REFERENCES accepted_graph_edges(id) ON DELETE CASCADE,
          evidence_annotation_id TEXT NOT NULL,
          chunk_id TEXT NOT NULL DEFAULT '',
          role TEXT NOT NULL DEFAULT 'supporting',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(edge_id, evidence_annotation_id, role)
        );

        CREATE TABLE IF NOT EXISTS relationship_evidence_review_items (
          id TEXT PRIMARY KEY,
          object_type TEXT NOT NULL,
          object_id TEXT NOT NULL,
          reason TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'open',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS relationship_evidence_query_traces (
          id TEXT PRIMARY KEY,
          query TEXT NOT NULL,
          planner_json TEXT NOT NULL DEFAULT '{}',
          result_count INTEGER NOT NULL DEFAULT 0,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_accepted_graph_edges_subject ON accepted_graph_edges(subject_entity_id, subject_text);
        CREATE INDEX IF NOT EXISTS idx_accepted_graph_edges_predicate ON accepted_graph_edges(predicate, status);
        CREATE INDEX IF NOT EXISTS idx_accepted_graph_edges_object ON accepted_graph_edges(object_entity_id, object_value);
        CREATE INDEX IF NOT EXISTS idx_accepted_graph_evidence_annotation ON accepted_graph_edge_evidence(evidence_annotation_id);
        CREATE INDEX IF NOT EXISTS idx_relationship_evidence_review_status ON relationship_evidence_review_items(status);
        """
    )
