-- v0.4 project intelligence. Additive CREATE only.
-- Formula champion is model_runs id=1 (formula-v1). Labels stay off intel_scores.

CREATE TABLE model_runs (
  id                INTEGER PRIMARY KEY,
  name              TEXT NOT NULL,
  trained_at        TEXT NOT NULL,
  train_cutoff_date TEXT,
  metrics_json      TEXT NOT NULL DEFAULT '{}',
  artifact_path     TEXT,
  status            TEXT NOT NULL CHECK (status IN ('trained','active','retired'))
);

CREATE TABLE intel_scores (
  id              INTEGER PRIMARY KEY,
  repo_id         INTEGER NOT NULL REFERENCES repos(id),
  as_of_date      TEXT NOT NULL,
  model_run_id    INTEGER REFERENCES model_runs(id),
  score           REAL,              -- EEV 0-100 or NULL
  components_json TEXT NOT NULL DEFAULT '{}',  -- potential/creator_prior/openness/entry_fit/confidence/sample/policy
  scored_at       TEXT NOT NULL,
  UNIQUE (repo_id, as_of_date, model_run_id)
);
CREATE INDEX idx_intel_scores_repo ON intel_scores(repo_id, as_of_date);
CREATE INDEX idx_intel_scores_date ON intel_scores(as_of_date);

CREATE TABLE outcome_labels (
  repo_id            INTEGER NOT NULL REFERENCES repos(id),
  as_of_date         TEXT NOT NULL,
  horizon_days       INTEGER NOT NULL CHECK (horizon_days IN (7,30,90)),
  stars_t            INTEGER,
  stars_t_h          INTEGER,        -- NULL if missing horizon snapshot
  delta_stars        INTEGER,        -- NULL if either stars missing; never 0-fill
  contributors_t     INTEGER,
  contributors_t_h   INTEGER,
  delta_contributors INTEGER,        -- NULL if either missing
  still_maintained   INTEGER,        -- 0/1/NULL
  source             TEXT,           -- exact | nearest-1d | NULL
  labeled_at         TEXT,
  PRIMARY KEY (repo_id, as_of_date, horizon_days)
);

INSERT INTO model_runs (id, name, trained_at, status)
VALUES (1, 'formula-v1', '1970-01-01T00:00:00+00:00', 'active');
