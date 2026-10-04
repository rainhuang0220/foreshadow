-- Owner-only traffic days. Values stay null when GitHub omitted them.
-- This table does not store tokens or public star/fork snapshots.
CREATE TABLE owner_traffic_observations (
  identity    TEXT NOT NULL,
  source      TEXT NOT NULL CHECK (source IN ('views', 'clones', 'referrers', 'paths')),
  observed_on TEXT NOT NULL,
  metric      TEXT NOT NULL,
  value       INTEGER,
  fetched_at  TEXT NOT NULL,
  PRIMARY KEY (identity, source, metric, observed_on)
);
