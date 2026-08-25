-- Entry missions. Local setup only. Remote GitHub writes require explicit user approval.

CREATE TABLE entry_missions (
  id            INTEGER PRIMARY KEY,
  user_id       INTEGER NOT NULL REFERENCES users(id),
  repo_id       INTEGER REFERENCES repos(id),
  full_name     TEXT NOT NULL,
  status        TEXT NOT NULL,
  entry_path    TEXT NOT NULL,
  difficulty    TEXT,
  effort        TEXT,
  plan_json     TEXT NOT NULL,
  local_path    TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE INDEX entry_missions_user ON entry_missions(user_id, updated_at);
CREATE INDEX entry_missions_repo ON entry_missions(full_name);
