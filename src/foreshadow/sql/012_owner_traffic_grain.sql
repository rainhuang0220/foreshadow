-- Grain tells a returned traffic day from a fetch-dated window.
-- Rows copied from schema 11: referrers and paths are windows; views and clones are days.
CREATE TABLE owner_traffic_observations_v2 (
  identity    TEXT NOT NULL,
  source      TEXT NOT NULL CHECK (source IN ('views', 'clones', 'referrers', 'paths')),
  observed_on TEXT NOT NULL,
  metric      TEXT NOT NULL,
  value       INTEGER,
  fetched_at  TEXT NOT NULL,
  grain       TEXT NOT NULL CHECK (grain IN ('day', 'window')),
  PRIMARY KEY (identity, source, metric, observed_on)
);

INSERT INTO owner_traffic_observations_v2 (
  identity, source, observed_on, metric, value, fetched_at, grain
)
SELECT
  identity,
  source,
  observed_on,
  metric,
  value,
  fetched_at,
  CASE WHEN source IN ('referrers', 'paths') THEN 'window' ELSE 'day' END
FROM owner_traffic_observations;

DROP TABLE owner_traffic_observations;
ALTER TABLE owner_traffic_observations_v2 RENAME TO owner_traffic_observations;
