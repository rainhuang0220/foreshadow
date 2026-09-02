-- v0.3: GitHub identity, observation events, entry analyses, contribution jobs.
-- Does not drop password users. Remote GitHub writes stay a later gate.

ALTER TABLE users ADD COLUMN github_id INTEGER;
ALTER TABLE users ADD COLUMN github_login TEXT;
CREATE UNIQUE INDEX idx_users_github_id ON users(github_id) WHERE github_id IS NOT NULL;
CREATE UNIQUE INDEX idx_users_github_login ON users(github_login COLLATE NOCASE) WHERE github_login IS NOT NULL;

ALTER TABLE sessions ADD COLUMN auth_method TEXT NOT NULL DEFAULT 'password';

CREATE TABLE oauth_states (
  state      TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  next_path  TEXT
);
CREATE INDEX idx_oauth_states_expires ON oauth_states(expires_at);

CREATE TABLE observation_events (
  id           INTEGER PRIMARY KEY,
  repo_id      INTEGER NOT NULL REFERENCES repos(id),
  occurred_on  TEXT NOT NULL,
  kind         TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE (repo_id, occurred_on, kind)
);
CREATE INDEX idx_observation_events_repo ON observation_events(repo_id, occurred_on);

CREATE TABLE entry_analyses (
  id                   INTEGER PRIMARY KEY,
  repo_id              INTEGER NOT NULL UNIQUE REFERENCES repos(id),
  analyzed_at          TEXT NOT NULL,
  stale_after          TEXT NOT NULL,
  source_snapshot_date TEXT,
  policy_json          TEXT NOT NULL,
  recommended_json     TEXT NOT NULL,
  alternatives_json    TEXT NOT NULL,
  evidence_json        TEXT NOT NULL,
  confidence           REAL
);

CREATE TABLE contribution_jobs (
  id         INTEGER PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id),
  repo_id    INTEGER REFERENCES repos(id),
  full_name  TEXT NOT NULL,
  status     TEXT NOT NULL,
  backend    TEXT NOT NULL,
  task_json  TEXT NOT NULL,
  log_json   TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_contribution_jobs_user ON contribution_jobs(user_id, updated_at);

CREATE TABLE contribution_artifacts (
  id         INTEGER PRIMARY KEY,
  job_id     INTEGER NOT NULL REFERENCES contribution_jobs(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL,
  path       TEXT,
  body       TEXT,
  meta_json  TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX idx_contribution_artifacts_job ON contribution_artifacts(job_id);
