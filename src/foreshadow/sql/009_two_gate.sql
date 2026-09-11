-- Two-gate contribution: mission-bound jobs, immutable approval, idempotent submit.

ALTER TABLE contribution_jobs ADD COLUMN mission_id INTEGER REFERENCES entry_missions(id);
CREATE INDEX idx_contribution_jobs_mission ON contribution_jobs(mission_id);

CREATE TABLE approval_snapshots (
  id              INTEGER PRIMARY KEY,
  user_id         INTEGER NOT NULL REFERENCES users(id),
  mission_id      INTEGER NOT NULL REFERENCES entry_missions(id),
  digest          TEXT NOT NULL,
  snapshot_json   TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'current',
  created_at      TEXT NOT NULL,
  invalidated_at  TEXT
);
CREATE INDEX idx_approval_snapshots_mission ON approval_snapshots(mission_id, status);

CREATE TABLE submissions (
  id                     INTEGER PRIMARY KEY,
  user_id                INTEGER NOT NULL REFERENCES users(id),
  mission_id             INTEGER NOT NULL REFERENCES entry_missions(id),
  approval_snapshot_id   INTEGER NOT NULL REFERENCES approval_snapshots(id),
  status                 TEXT NOT NULL,
  steps_json             TEXT NOT NULL DEFAULT '{}',
  result_json            TEXT NOT NULL DEFAULT '{}',
  created_at             TEXT NOT NULL,
  updated_at             TEXT NOT NULL
);
CREATE INDEX idx_submissions_mission ON submissions(mission_id);
