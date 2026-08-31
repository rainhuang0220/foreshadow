-- P1 system observation panel. Not user reviews or watch stances.
-- Identity is repos.id (node_id). User watchlist stays in reviews.

CREATE TABLE observations (
  repo_id           INTEGER PRIMARY KEY REFERENCES repos(id),
  added_on          TEXT NOT NULL,     -- UTC YYYY-MM-DD first promotion
  last_observed_on  TEXT NOT NULL,     -- UTC day of last successful snapshot
  expires_on        TEXT NOT NULL,     -- added_on + observation_ttl_days; not sliding
  reason            TEXT NOT NULL,     -- admission reason, not a user stance
  state             TEXT NOT NULL DEFAULT 'active'
                    CHECK (state IN ('active', 'expired'))
);

CREATE INDEX idx_observations_state_expires ON observations(state, expires_on);
CREATE INDEX idx_observations_added ON observations(added_on, repo_id);
