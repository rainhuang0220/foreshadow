-- P1 user isolation. Public scores stay in repos/snapshots/scores.
-- Reviews become per-user. CLI uses the single is_local operator.

CREATE TABLE users (
  id            INTEGER PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  is_local      INTEGER NOT NULL DEFAULT 0 CHECK (is_local IN (0, 1))
);
CREATE UNIQUE INDEX idx_users_one_local ON users(is_local) WHERE is_local = 1;

CREATE TABLE sessions (
  id           INTEGER PRIMARY KEY,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash   TEXT NOT NULL UNIQUE,
  created_at   TEXT NOT NULL,
  expires_at   TEXT NOT NULL,
  last_seen_at TEXT
);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);

ALTER TABLE reviews ADD COLUMN user_id INTEGER REFERENCES users(id);
CREATE INDEX idx_reviews_user_repo_time ON reviews(user_id, repo_id, created_at DESC);
