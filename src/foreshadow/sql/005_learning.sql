-- S5 learning loop. Outcomes of our entries, not third-party writes.

CREATE TABLE contribution_events (
  id          INTEGER PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  mission_id  INTEGER REFERENCES entry_missions(id),
  full_name   TEXT NOT NULL,
  event       TEXT NOT NULL,
  detail_json TEXT,
  created_at  TEXT NOT NULL
);

CREATE INDEX contribution_events_user ON contribution_events(user_id, created_at);
