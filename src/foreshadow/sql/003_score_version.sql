-- Rebuild scores: one row per (run, repo, version). Copy existing rows as v1.
-- scores is not referenced by other FKs; DROP is safe with foreign_keys=ON.
-- Official selected_rank stays on v1 until owner cutover. Never UPDATE v1 into v2.

CREATE TABLE scores__v3 (
  id                INTEGER PRIMARY KEY,
  run_id            INTEGER NOT NULL REFERENCES daily_runs(id) ON DELETE CASCADE,
  repo_id           INTEGER NOT NULL REFERENCES repos(id),
  score_version     TEXT NOT NULL DEFAULT 'v1'
                    CHECK (score_version IN ('v1', 'v2')),
  opportunity       REAL,
  explosion         REAL,
  contribution      REAL,
  confidence        TEXT NOT NULL
                    CHECK (confidence IN ('low','medium','high')),
  components_json   TEXT NOT NULL,
  evidence_json     TEXT NOT NULL,
  flags_json        TEXT NOT NULL,
  vetoed            INTEGER NOT NULL DEFAULT 0,
  veto_reason       TEXT,
  exceptional       TEXT,
  selected_rank     INTEGER,
  pool_rank         INTEGER,
  scored_at         TEXT NOT NULL,
  UNIQUE (run_id, repo_id, score_version)
);

INSERT INTO scores__v3 (
  id, run_id, repo_id, score_version,
  opportunity, explosion, contribution, confidence,
  components_json, evidence_json, flags_json,
  vetoed, veto_reason, exceptional, selected_rank, pool_rank, scored_at
)
SELECT
  id, run_id, repo_id, 'v1',
  opportunity, explosion, contribution, confidence,
  components_json, evidence_json, flags_json,
  vetoed, veto_reason, exceptional, selected_rank, NULL, scored_at
FROM scores;

DROP TABLE scores;
ALTER TABLE scores__v3 RENAME TO scores;

CREATE INDEX idx_scores_rank ON scores(run_id, score_version, selected_rank);
CREATE INDEX idx_scores_pool ON scores(run_id, score_version, pool_rank);
CREATE INDEX idx_scores_repo ON scores(repo_id, scored_at DESC);

CREATE TABLE score_compare (
  run_id          INTEGER NOT NULL REFERENCES daily_runs(id) ON DELETE CASCADE,
  repo_id         INTEGER NOT NULL REFERENCES repos(id),
  v1_rank         INTEGER,
  v2_rank         INTEGER,
  rank_delta      INTEGER,
  v1_opportunity  REAL,
  v2_opportunity  REAL,
  UNIQUE (run_id, repo_id)
);
CREATE INDEX idx_score_compare_delta ON score_compare(run_id, rank_delta);
