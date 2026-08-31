CREATE TABLE schema_migrations (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE repos (
  id            INTEGER PRIMARY KEY,
  node_id       TEXT NOT NULL UNIQUE,   -- GraphQL global id (PK of identity)
  database_id   INTEGER UNIQUE,         -- REST / GraphQL databaseId
  full_name     TEXT NOT NULL UNIQUE,   -- current owner/name; mutated on rename
  owner         TEXT NOT NULL,
  name          TEXT NOT NULL,
  html_url      TEXT,
  description   TEXT,
  language      TEXT,
  license_spdx  TEXT,                   -- NULL / NOASSERTION / SPDX; NOASSERTION ≡ null for H9
  created_at    TEXT,                   -- repo createdAt; age_days from this
  default_branch TEXT,
  has_issues    INTEGER,                -- 0/1/NULL
  is_fork       INTEGER NOT NULL DEFAULT 0,
  is_archived   INTEGER NOT NULL DEFAULT 0,
  is_disabled   INTEGER NOT NULL DEFAULT 0,
  is_empty      INTEGER NOT NULL DEFAULT 0,
  is_template   INTEGER NOT NULL DEFAULT 0,
  is_mirror     INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','not_found','private','incomplete')),
  first_seen_at TEXT NOT NULL,
  last_seen_at  TEXT NOT NULL
);

CREATE TABLE repo_aliases (
  id         INTEGER PRIMARY KEY,
  repo_id    INTEGER NOT NULL REFERENCES repos(id),
  full_name  TEXT NOT NULL,
  seen_at    TEXT NOT NULL,
  UNIQUE (repo_id, full_name)
);
CREATE INDEX idx_aliases_name ON repo_aliases(full_name);

-- One row per repo per UTC date. Re-run upserts. This table IS star history.
CREATE TABLE snapshots (
  id                       INTEGER PRIMARY KEY,
  repo_id                  INTEGER NOT NULL REFERENCES repos(id),
  snapshot_date            TEXT NOT NULL,     -- YYYY-MM-DD UTC
  captured_at              TEXT NOT NULL,     -- ISO-8601 UTC
  stars                    INTEGER,           -- stargazerCount
  forks                    INTEGER,           -- forkCount
  open_issues              INTEGER,           -- GraphQL issues OPEN totalCount; NEVER REST open_issues_count
  closed_issues            INTEGER,
  open_prs                 INTEGER,           -- GraphQL pullRequests OPEN totalCount
  watchers                 INTEGER,           -- unused in P0; always NULL. Do not query GraphQL watchers or REST subscribers. NEVER watchers_count.
  last_pushed_at           TEXT,
  last_commit_at           TEXT,              -- default-branch committedDate
  contributor_count        INTEGER,           -- C = identified + anon; NULL = unknown
  contributor_identified   INTEGER,
  contributor_anon         INTEGER,
  contributor_censored     INTEGER,           -- 1 iff 500 identified users
  unique_committers_30d    INTEGER,           -- UNIQUE human authors; NOT commit count
  discussions_count        INTEGER,
  topics_json              TEXT NOT NULL DEFAULT '[]',
  features_json            TEXT NOT NULL DEFAULT '{}',  -- deep hydrate blob (issues sample, README, tree)
  completeness             REAL NOT NULL,     -- 0-1
  UNIQUE (repo_id, snapshot_date)
);
CREATE INDEX idx_snapshots_date ON snapshots(snapshot_date);
CREATE INDEX idx_snapshots_repo ON snapshots(repo_id, snapshot_date);

CREATE TABLE daily_runs (
  id                 INTEGER PRIMARY KEY,
  run_date           TEXT NOT NULL UNIQUE,
  started_at         TEXT NOT NULL,
  finished_at        TEXT,
  status             TEXT NOT NULL
                     CHECK (status IN ('running','complete','degraded','failed')),
  config_hash        TEXT,
  source_health_json TEXT NOT NULL DEFAULT '{}',
  budget_used        INTEGER NOT NULL DEFAULT 0,   -- GraphQL points actually billed
  budget_rest_used   INTEGER NOT NULL DEFAULT 0,
  budget_cap         INTEGER NOT NULL,             -- GraphQL cap (default 800). REST cap is config-only.
  candidate_count    INTEGER,
  scored_count       INTEGER,
  top5_count         INTEGER,                      -- 0..5
  report_path        TEXT,
  error              TEXT
);

CREATE TABLE candidates (
  id                INTEGER PRIMARY KEY,
  run_id            INTEGER NOT NULL REFERENCES daily_runs(id) ON DELETE CASCADE,
  repo_id           INTEGER NOT NULL REFERENCES repos(id),
  discovery_source  TEXT NOT NULL,     -- see precedence: active > watchlist > search:<key>; joined with '+'
  hydrate_status    TEXT NOT NULL
                    CHECK (hydrate_status IN ('ok','incomplete','not_found','failed')),
  UNIQUE (run_id, repo_id)
);

CREATE TABLE scores (
  id                INTEGER PRIMARY KEY,
  run_id            INTEGER NOT NULL REFERENCES daily_runs(id) ON DELETE CASCADE,
  repo_id           INTEGER NOT NULL REFERENCES repos(id),
  opportunity       REAL,              -- 0-100; NULL if not scorable
  explosion         REAL,              -- 0-100; NULL if H-rejected OR v7 NA (lifetime proxy is evidence-only)
  contribution      REAL,              -- 0-100 ContributionScore == ContributionOpp
  confidence        TEXT NOT NULL
                    CHECK (confidence IN ('low','medium','high')),
  components_json   TEXT NOT NULL,     -- see Evidence JSON
  evidence_json     TEXT NOT NULL,
  flags_json        TEXT NOT NULL,     -- ["is_accelerating","bus_factor","H5","P1",...]
  vetoed            INTEGER NOT NULL DEFAULT 0,
  veto_reason       TEXT,              -- comma-joined fired H-ids in H1..H10 order, e.g. "H5,H6,H7"
  exceptional       TEXT,              -- NULL | off_direction_but_strong | exceptional_override | exceptional_override_weak_fit
  selected_rank     INTEGER,           -- 1..5 or NULL
  scored_at         TEXT NOT NULL,
  UNIQUE (run_id, repo_id)
);
CREATE INDEX idx_scores_rank ON scores(run_id, selected_rank);

-- Append-only. Latest row per repo_id is current stance.
CREATE TABLE reviews (
  id         INTEGER PRIMARY KEY,
  repo_id    INTEGER NOT NULL REFERENCES repos(id),
  action     TEXT NOT NULL
             CHECK (action IN ('watch','interested','reject','investigate','enter','later')),
  note       TEXT,
  run_id     INTEGER REFERENCES daily_runs(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_reviews_repo_time ON reviews(repo_id, created_at DESC);

-- Filled on action=enter. PK = repo. P0 stores the row; growth refresh is the daily snapshot join.
CREATE TABLE entries (
  repo_id                  INTEGER PRIMARY KEY REFERENCES repos(id),
  entered_at               TEXT NOT NULL,
  run_id                   INTEGER REFERENCES daily_runs(id),
  stars_at_entry           INTEGER,
  contributors_at_entry    INTEGER,
  open_issues_at_entry     INTEGER,
  opportunity_at_entry     REAL,
  explosion_at_entry       REAL,
  contribution_at_entry    REAL,
  scores_at_entry_json     TEXT NOT NULL,
  chosen_contribution      TEXT,
  note                     TEXT
);

CREATE TABLE source_failures (
  id          INTEGER PRIMARY KEY,
  run_id      INTEGER NOT NULL REFERENCES daily_runs(id) ON DELETE CASCADE,
  source      TEXT NOT NULL,
  reason      TEXT NOT NULL,           -- rate_limit | http_404 | http_5xx | timeout | decode | budget | graphql_error
  detail      TEXT,                    -- NEVER contains Authorization
  retryable   INTEGER NOT NULL DEFAULT 1,
  occurred_at TEXT NOT NULL
);

CREATE TABLE raw_payloads (
  id          INTEGER PRIMARY KEY,
  run_id      INTEGER REFERENCES daily_runs(id) ON DELETE SET NULL,
  kind        TEXT NOT NULL,           -- search | hydrate | rest
  cache_key   TEXT NOT NULL,
  etag        TEXT,
  fetched_at  TEXT NOT NULL,
  http_status INTEGER,
  body        TEXT NOT NULL
);
CREATE INDEX idx_raw_key ON raw_payloads(cache_key, fetched_at DESC);
