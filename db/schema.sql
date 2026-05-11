PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  year INTEGER,
  source_type TEXT NOT NULL,
  venue TEXT,
  url TEXT,
  arxiv_id TEXT,
  repo_url TEXT,
  primary_focus TEXT,
  agent_relevance INTEGER NOT NULL DEFAULT 0,
  engineering_relevance INTEGER NOT NULL DEFAULT 0,
  evidence_strength INTEGER NOT NULL DEFAULT 0,
  reproducibility INTEGER NOT NULL DEFAULT 0,
  safety_relevance INTEGER NOT NULL DEFAULT 0,
  summary TEXT NOT NULL,
  critical_notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'seeded',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS source_tags (
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (source_id, tag_id)
);

CREATE TABLE IF NOT EXISTS patterns (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  description TEXT NOT NULL,
  agent_rule TEXT NOT NULL,
  runtime_rule TEXT NOT NULL DEFAULT '',
  maturity TEXT NOT NULL DEFAULT 'emerging'
);

CREATE TABLE IF NOT EXISTS source_patterns (
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  pattern_id TEXT NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
  note TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (source_id, pattern_id)
);

CREATE TABLE IF NOT EXISTS failure_modes (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  detection TEXT NOT NULL,
  mitigation TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'medium'
);

CREATE TABLE IF NOT EXISTS source_failure_modes (
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  failure_mode_id TEXT NOT NULL REFERENCES failure_modes(id) ON DELETE CASCADE,
  note TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (source_id, failure_mode_id)
);

CREATE TABLE IF NOT EXISTS benchmarks (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  domain TEXT NOT NULL,
  url TEXT,
  measures TEXT NOT NULL,
  strengths TEXT NOT NULL,
  limitations TEXT NOT NULL,
  agent_use TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  claim TEXT NOT NULL,
  evidence TEXT NOT NULL,
  limitation TEXT NOT NULL DEFAULT '',
  agent_implication TEXT NOT NULL DEFAULT '',
  confidence TEXT NOT NULL DEFAULT 'medium'
);

CREATE TABLE IF NOT EXISTS agent_practices (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  trigger TEXT NOT NULL,
  practice TEXT NOT NULL,
  anti_pattern TEXT NOT NULL DEFAULT '',
  evidence_basis TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS skill_cards (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  purpose TEXT NOT NULL,
  trigger TEXT NOT NULL,
  workflow TEXT NOT NULL,
  source_basis TEXT NOT NULL DEFAULT ''
);
