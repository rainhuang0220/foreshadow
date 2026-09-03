import ast
import importlib.resources
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from random import Random

import pytest

from fakes import seed_repo
from foreshadow.db import connect, migrate
from foreshadow.pipeline.bandit import shadow_explore
from foreshadow.pipeline.labels import lookup_horizon_snapshot, resolve_labels
from foreshadow.pipeline.trainer import (
    LABELED_JOIN_SQL,
    extract_snapshot_features,
    load_labeled_rows,
    open_readonly,
    repo_only,
    repo_plus_creator,
    repo_plus_openness,
    train_challenger,
)

_FALLBACK_008 = """
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
  score           REAL,
  components_json TEXT NOT NULL DEFAULT '{}',
  scored_at       TEXT NOT NULL,
  UNIQUE (repo_id, as_of_date, model_run_id)
);
CREATE TABLE outcome_labels (
  repo_id            INTEGER NOT NULL REFERENCES repos(id),
  as_of_date         TEXT NOT NULL,
  horizon_days       INTEGER NOT NULL CHECK (horizon_days IN (7,30,90)),
  stars_t            INTEGER,
  stars_t_h          INTEGER,
  delta_stars        INTEGER,
  contributors_t     INTEGER,
  contributors_t_h   INTEGER,
  delta_contributors INTEGER,
  still_maintained   INTEGER,
  source             TEXT,
  labeled_at         TEXT,
  PRIMARY KEY (repo_id, as_of_date, horizon_days)
);
INSERT INTO model_runs (id, name, trained_at, status)
VALUES (1, 'formula-v1', '1970-01-01T00:00:00+00:00', 'active');
"""


def _db(tmp_home):
    path = tmp_home / "foreshadow.sqlite3"
    conn = connect(path)
    migrate(conn)
    _ensure_learning_tables(conn)
    return conn, path


def _ensure_learning_tables(conn):
    names = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "outcome_labels" in names:
        return
    try:
        sql = (
            importlib.resources.files("foreshadow")
            .joinpath("sql/008_project_intelligence.sql")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        sql = _FALLBACK_008
    conn.executescript(sql)
    conn.commit()


def _snap(
    conn,
    repo_id,
    day,
    *,
    stars=None,
    forks=0,
    contributor_count=None,
    last_pushed_at=None,
    features_json="{}",
):
    day_s = day.isoformat() if isinstance(day, date) else str(day)
    conn.execute(
        """
        INSERT INTO snapshots(
          repo_id, snapshot_date, captured_at, stars, forks,
          contributor_count, last_pushed_at, features_json, completeness
        ) VALUES (?,?,?,?,?,?,?,?,1)
        """,
        (
            repo_id,
            day_s,
            f"{day_s}T00:00:00+00:00",
            stars,
            forks,
            contributor_count,
            last_pushed_at,
            features_json,
        ),
    )


def _label_row(conn, repo_id, as_of, *, stars_t, delta, contributor_count=2):
    as_of_s = as_of.isoformat() if isinstance(as_of, date) else str(as_of)
    conn.execute(
        """
        INSERT INTO outcome_labels(
          repo_id, as_of_date, horizon_days, stars_t, stars_t_h, delta_stars,
          contributors_t, contributors_t_h, delta_contributors, source, labeled_at
        ) VALUES (?, ?, 30, ?, ?, ?, ?, ?, 0, 'exact', 't')
        """,
        (
            repo_id,
            as_of_s,
            stars_t,
            stars_t + delta,
            delta,
            contributor_count,
            contributor_count,
        ),
    )


def test_missing_horizon_stays_null_not_zero(tmp_home):
    conn, _ = _db(tmp_home)
    today = date(2026, 9, 3)
    as_of = today - timedelta(days=30)
    rid = seed_repo(conn, "R_miss", "acme/miss")
    _snap(
        conn,
        rid,
        as_of,
        stars=100,
        contributor_count=4,
        last_pushed_at="2026-08-01T00:00:00Z",
    )
    _snap(conn, rid, today - timedelta(days=1), stars=0, contributor_count=0)
    written = resolve_labels(conn, today)
    assert written >= 1
    row = conn.execute(
        """
        SELECT stars_t, stars_t_h, delta_stars, contributors_t, contributors_t_h,
               delta_contributors, source, still_maintained
        FROM outcome_labels
        WHERE repo_id=? AND horizon_days=30
        """,
        (rid,),
    ).fetchone()
    assert row[0] == 100
    assert row[1] is None
    assert row[2] is None
    assert row[2] != 0
    assert row[3] == 4
    assert row[4] is None
    assert row[5] is None
    assert row[6] is None
    assert row[7] is None
    assert lookup_horizon_snapshot(conn, rid, today, slack_days=1) is None


def test_real_zero_growth_stores_zero(tmp_home):
    conn, _ = _db(tmp_home)
    today = date(2026, 9, 3)
    as_of = today - timedelta(days=30)
    rid = seed_repo(conn, "R_zero", "acme/zero")
    _snap(
        conn,
        rid,
        as_of,
        stars=80,
        contributor_count=5,
        last_pushed_at="2026-07-01T00:00:00Z",
    )
    _snap(
        conn,
        rid,
        today,
        stars=80,
        contributor_count=5,
        last_pushed_at="2026-08-20T00:00:00Z",
    )
    resolve_labels(conn, today)
    row = conn.execute(
        """
        SELECT stars_t, stars_t_h, delta_stars, contributors_t, contributors_t_h,
               delta_contributors, source
        FROM outcome_labels
        WHERE repo_id=? AND horizon_days=30
        """,
        (rid,),
    ).fetchone()
    assert row[0] == 80
    assert row[1] == 80
    assert row[2] == 0
    assert row[2] is not None
    assert row[3] == 5
    assert row[4] == 5
    assert row[5] == 0
    assert row[6] == "exact"


def test_horizon_lookup_is_forward_nearest(tmp_home):
    conn, _ = _db(tmp_home)
    today = date(2026, 9, 3)
    as_of = today - timedelta(days=30)
    rid = seed_repo(conn, "R_near", "acme/near")
    _snap(conn, rid, as_of, stars=10, contributor_count=2)
    _snap(conn, rid, today + timedelta(days=1), stars=18, contributor_count=3)
    resolve_labels(conn, today)
    row = conn.execute(
        """
        SELECT stars_t_h, delta_stars, source
        FROM outcome_labels
        WHERE repo_id=? AND horizon_days=30
        """,
        (rid,),
    ).fetchone()
    assert row[0] == 18
    assert row[1] == 8
    assert row[2] == "nearest-1d"


def test_trainer_readonly_sqlite(tmp_home):
    conn, path = _db(tmp_home)
    conn.close()
    ro = open_readonly(path)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("UPDATE model_runs SET status='retired' WHERE id=1")
    ro.close()


def test_trainer_sklearn_missing_is_skipped(monkeypatch, tmp_path):
    import sys

    monkeypatch.setitem(sys.modules, "sklearn", None)
    monkeypatch.setitem(sys.modules, "sklearn.ensemble", None)
    monkeypatch.setitem(sys.modules, "sklearn.metrics", None)
    from foreshadow.pipeline.trainer import train_challenger as train

    out = train(tmp_path / "missing.sqlite3", tmp_path / "artifacts")
    assert out["status"] == "skipped"
    assert out["reason"] == "sklearn"


def test_trainer_source_does_not_import_github():
    from foreshadow.pipeline import trainer as trainer_mod

    src = Path(trainer_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "github" not in alias.name.lower()
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").lower()
            assert "github" not in mod
            for alias in node.names:
                assert "github" not in alias.name.lower()
    assert "foreshadow.github" not in src


def test_bandit_does_not_reorder_ranked():
    ranked = ["acme/one", "acme/two"]
    original = list(ranked)
    candidates = ["acme/one", "acme/two", "acme/three"]
    out = shadow_explore(candidates, ranked, epsilon=1.0, rng=Random(0))
    assert ranked == original
    assert ranked == ["acme/one", "acme/two"]
    assert candidates[0] == "acme/one"
    assert out["policy"] == "shadow_eps_greedy"
    assert out["mode"] == "shadow"
    assert out["epsilon"] == 1.0
    assert out["explored"] == "acme/three"
    none = shadow_explore(candidates, ranked, epsilon=0.0, rng=Random(0))
    assert none["explored"] is None
    assert ranked == original


def test_features_at_t_do_not_include_horizon_stars(tmp_home):
    assert "stars_t_h" not in LABELED_JOIN_SQL
    assert "s.snapshot_date = o.as_of_date" in LABELED_JOIN_SQL
    feats = extract_snapshot_features(
        stars=10,
        forks=1,
        contributor_count=2,
        features_json='{"stars_t_h": 999, "delta_stars": 50, "creator_age": 3}',
    )
    assert feats["stars"] == 10.0
    assert "stars_t_h" not in feats
    assert "delta_stars" not in feats

    conn, _ = _db(tmp_home)
    today = date(2026, 9, 3)
    as_of = today - timedelta(days=30)
    rid = seed_repo(conn, "R_leak", "acme/leak")
    _snap(
        conn,
        rid,
        as_of,
        stars=10,
        forks=1,
        contributor_count=2,
        features_json=json.dumps({"commits_7d": 4, "stars_t_h": 999}),
    )
    _snap(conn, rid, today, stars=999, contributor_count=9)
    resolve_labels(conn, today)
    rows = load_labeled_rows(conn)
    assert len(rows) == 1
    assert rows[0]["features"]["stars"] == 10.0
    assert rows[0]["features"].get("commits_7d") == 4.0
    assert "stars_t_h" not in rows[0]["features"]
    assert rows[0]["delta_stars"] == 989


def test_ablation_hooks_drop_creator_and_openness_keys():
    feats = {
        "stars": 12.0,
        "forks": 2.0,
        "creator_public_repos": 4.0,
        "openness_wilson": 0.3,
    }
    only = repo_only(feats)
    assert only == {"stars": 12.0, "forks": 2.0}
    plus_c = repo_plus_creator(feats)
    assert plus_c["creator_public_repos"] == 4.0
    assert "openness_wilson" not in plus_c
    plus_o = repo_plus_openness(feats)
    assert plus_o["openness_wilson"] == 0.3
    assert "creator_public_repos" not in plus_o
    assert feats["creator_public_repos"] == 4.0


def test_trainer_few_samples_skipped(tmp_home):
    pytest.importorskip("sklearn")
    conn, path = _db(tmp_home)
    as_of = date(2026, 6, 1)
    for i in range(5):
        rid = seed_repo(conn, f"R_few{i}", f"acme/few{i}")
        _snap(conn, rid, as_of, stars=10 + i, contributor_count=2)
        _label_row(conn, rid, as_of, stars_t=10 + i, delta=2)
    conn.commit()
    conn.close()
    out = train_challenger(path, tmp_home / "art", cutoff_date=date(2026, 7, 1))
    assert out["status"] == "skipped"
    assert out["reason"] == "few_samples"
    assert out["n"] == 5


def test_trainer_does_not_promote_formula_champion(tmp_home):
    pytest.importorskip("sklearn")
    conn, path = _db(tmp_home)
    _seed_train_panel(conn, n=20, as_of=date(2026, 6, 1), start=0)
    _seed_train_panel(conn, n=20, as_of=date(2026, 8, 1), start=20)
    conn.commit()
    conn.close()
    out = train_challenger(path, tmp_home / "art", cutoff_date=date(2026, 7, 1))
    assert out["status"] == "trained"
    assert out["promoted"] is False
    assert out["champion"] == "formula-v1"
    conn = connect(path)
    formula = conn.execute("SELECT name, status FROM model_runs WHERE id=1").fetchone()
    assert formula == ("formula-v1", "active")
    active_n = conn.execute(
        "SELECT COUNT(*) FROM model_runs WHERE status='active'"
    ).fetchone()[0]
    assert active_n == 1
    trained = conn.execute("SELECT status FROM model_runs WHERE id>1").fetchall()
    assert trained
    assert all(row[0] == "trained" for row in trained)


def _seed_train_panel(conn, *, n: int, as_of: date, start: int) -> None:
    for i in range(n):
        idx = start + i
        rid = seed_repo(conn, f"R_tr{idx}", f"acme/tr{idx}")
        stars_t = 10 + (idx % 7)
        delta = 4 if idx % 2 == 0 else 0
        _snap(
            conn,
            rid,
            as_of,
            stars=stars_t,
            forks=1,
            contributor_count=2 + (idx % 4),
            features_json=json.dumps(
                {
                    "commits_7d": idx % 9,
                    "creator_public_repos": idx % 5,
                    "openness_n_ext": 8 + (idx % 3),
                }
            ),
        )
        _label_row(conn, rid, as_of, stars_t=stars_t, delta=delta)
