CREATE TABLE IF NOT EXISTS global_scores (
  mode TEXT PRIMARY KEY CHECK (mode IN ('classic', 'arcade', 'zen', 'path')),
  score INTEGER NOT NULL DEFAULT 0 CHECK (score >= 0),
  updated_at INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO global_scores (mode, score, updated_at) VALUES
  ('classic', 0, 0), ('arcade', 0, 0), ('zen', 0, 0), ('path', 0, 0);

CREATE TABLE IF NOT EXISTS used_nonces (
  nonce TEXT PRIMARY KEY,
  expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS used_nonces_expiry ON used_nonces (expires_at);

CREATE TABLE IF NOT EXISTS submission_limits (
  source_hash TEXT PRIMARY KEY,
  window_start INTEGER NOT NULL,
  submissions INTEGER NOT NULL CHECK (submissions >= 1)
);
