PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  confidence TEXT NOT NULL DEFAULT 'medium',
  status TEXT NOT NULL DEFAULT 'active',
  source_ref TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY,
  evidence_type TEXT NOT NULL,
  title TEXT NOT NULL,
  source_path TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  locator TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  confidence TEXT NOT NULL DEFAULT 'medium',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS edges (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  relation TEXT NOT NULL,
  target_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  evidence_id TEXT REFERENCES evidence(id) ON DELETE SET NULL,
  summary TEXT NOT NULL DEFAULT '',
  confidence TEXT NOT NULL DEFAULT 'medium',
  weight REAL NOT NULL DEFAULT 1.0,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(source_id, relation, target_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS aliases (
  node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  PRIMARY KEY (node_id, alias)
);

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS node_tags (
  node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (node_id, tag_id)
);

CREATE TABLE IF NOT EXISTS source_registry (
  id TEXT PRIMARY KEY,
  url TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL,
  source_type TEXT NOT NULL DEFAULT 'unknown',
  canonical_ref TEXT NOT NULL DEFAULT '',
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_checked_at TEXT,
  freshness_window_days INTEGER NOT NULL DEFAULT 30,
  status TEXT NOT NULL DEFAULT 'active',
  credibility_score INTEGER NOT NULL DEFAULT 0,
  current_capture_id TEXT,
  notes TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_captures (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES source_registry(id) ON DELETE CASCADE,
  retrieved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  content_hash TEXT NOT NULL,
  raw_path TEXT NOT NULL DEFAULT '',
  summary_path TEXT NOT NULL DEFAULT '',
  extraction_status TEXT NOT NULL DEFAULT 'captured',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS graph_update_proposals (
  id TEXT PRIMARY KEY,
  source_id TEXT REFERENCES source_registry(id) ON DELETE SET NULL,
  capture_id TEXT REFERENCES source_captures(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'proposed',
  risk_level TEXT NOT NULL DEFAULT 'medium',
  proposal_path TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  review_notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at TEXT,
  applied_at TEXT
);

CREATE TABLE IF NOT EXISTS graph_change_sets (
  id TEXT PRIMARY KEY,
  action TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'auto',
  source_id TEXT NOT NULL DEFAULT '',
  capture_id TEXT NOT NULL DEFAULT '',
  proposal_id TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  actor TEXT NOT NULL DEFAULT 'praxis',
  status TEXT NOT NULL DEFAULT 'applied',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reverted_at TEXT
);

CREATE TABLE IF NOT EXISTS graph_change_items (
  id TEXT PRIMARY KEY,
  change_set_id TEXT NOT NULL REFERENCES graph_change_sets(id) ON DELETE CASCADE,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS refresh_queue (
  id TEXT PRIMARY KEY,
  source_id TEXT REFERENCES source_registry(id) ON DELETE CASCADE,
  topic TEXT NOT NULL DEFAULT '',
  next_check_at TEXT,
  frequency_days INTEGER NOT NULL DEFAULT 30,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist_runs (
  id TEXT PRIMARY KEY,
  watchlist_name TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  query_count INTEGER NOT NULL DEFAULT 0,
  hit_count INTEGER NOT NULL DEFAULT 0,
  report_path TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS research_hits (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES watchlist_runs(id) ON DELETE CASCADE,
  watchlist_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  canonical_ref TEXT NOT NULL DEFAULT '',
  published_at TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT '',
  authors TEXT NOT NULL DEFAULT '',
  abstract TEXT NOT NULL DEFAULT '',
  venue TEXT NOT NULL DEFAULT '',
  categories TEXT NOT NULL DEFAULT '',
  score REAL NOT NULL DEFAULT 0.0,
  rank_reasons TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'new',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(alias);
CREATE INDEX IF NOT EXISTS idx_evidence_title ON evidence(title);
CREATE INDEX IF NOT EXISTS idx_source_registry_status ON source_registry(status);
CREATE INDEX IF NOT EXISTS idx_source_registry_last_checked ON source_registry(last_checked_at);
CREATE INDEX IF NOT EXISTS idx_source_captures_source ON source_captures(source_id);
CREATE INDEX IF NOT EXISTS idx_graph_update_proposals_status ON graph_update_proposals(status);
CREATE INDEX IF NOT EXISTS idx_graph_change_sets_status ON graph_change_sets(status);
CREATE INDEX IF NOT EXISTS idx_graph_change_sets_capture ON graph_change_sets(capture_id);
CREATE INDEX IF NOT EXISTS idx_graph_change_items_change_set ON graph_change_items(change_set_id);
CREATE INDEX IF NOT EXISTS idx_graph_change_items_object ON graph_change_items(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_refresh_queue_next_check ON refresh_queue(next_check_at);
CREATE INDEX IF NOT EXISTS idx_watchlist_runs_name ON watchlist_runs(watchlist_name);
CREATE INDEX IF NOT EXISTS idx_research_hits_run ON research_hits(run_id);
CREATE INDEX IF NOT EXISTS idx_research_hits_watchlist ON research_hits(watchlist_name);
CREATE INDEX IF NOT EXISTS idx_research_hits_score ON research_hits(score);
CREATE INDEX IF NOT EXISTS idx_research_hits_status ON research_hits(status);

DROP VIEW IF EXISTS edge_view;

CREATE VIEW edge_view AS
SELECT
  e.id,
  e.relation,
  e.confidence,
  e.weight,
  e.summary,
  e.status,
  e.status AS edge_status,
  e.source_id,
  s.name AS source_name,
  s.type AS source_type,
  s.status AS source_status,
  e.target_id,
  t.name AS target_name,
  t.type AS target_type,
  t.status AS target_status,
  e.evidence_id,
  ev.title AS evidence_title,
  ev.source_path AS evidence_source_path,
  ev.url AS evidence_url,
  ev.locator AS evidence_locator,
  ev.status AS evidence_status
FROM edges e
JOIN nodes s ON s.id = e.source_id
JOIN nodes t ON t.id = e.target_id
LEFT JOIN evidence ev ON ev.id = e.evidence_id;
