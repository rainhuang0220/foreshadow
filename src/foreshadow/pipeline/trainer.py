"""Offline challenger trainer. SQLite read-only. Never promotes over formula-v1."""

from __future__ import annotations

import json
import pickle
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

FORMULA_CHAMPION = "formula-v1"
MIN_SAMPLES = 30
MAX_TRAIN_ROWS = 5000
TRAIN_HORIZON_DAYS = 30
CHAMPION_EEV_THRESHOLD = 50.0
LEAK_FEATURE_KEYS = frozenset(
    {
        "stars_t_h",
        "delta_stars",
        "contributors_t_h",
        "delta_contributors",
        "still_maintained",
        "y",
        "label",
        "eev",
    }
)

# as_of snapshot only. Horizon outcomes are the label, never features.
LABELED_JOIN_SQL = """
SELECT
  o.repo_id,
  o.as_of_date,
  o.delta_stars,
  s.stars,
  s.forks,
  s.contributor_count,
  s.features_json
FROM outcome_labels o
JOIN snapshots s
  ON s.repo_id = o.repo_id
 AND s.snapshot_date = o.as_of_date
WHERE o.horizon_days = ?
  AND o.delta_stars IS NOT NULL
"""


def open_readonly(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def repo_only(features: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in features.items()
        if not key.startswith(("creator_", "openness_"))
    }


def repo_plus_creator(features: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in features.items() if not key.startswith("openness_")
    }


def repo_plus_openness(features: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in features.items() if not key.startswith("creator_")
    }


def extract_snapshot_features(
    *,
    stars: Any,
    forks: Any,
    contributor_count: Any,
    features_json: str | None,
) -> dict[str, float]:
    """Numeric features at as_of. Drops horizon labels even if present in JSON."""
    blob = _parse_features_json(features_json)
    feats = _numeric_items(blob)
    for key in list(feats):
        if key in LEAK_FEATURE_KEYS:
            del feats[key]
    _put_numeric(feats, "stars", stars)
    _put_numeric(feats, "forks", forks)
    _put_numeric(feats, "contributor_count", contributor_count)
    return feats


def load_labeled_rows(
    conn: sqlite3.Connection,
    *,
    horizon_days: int = TRAIN_HORIZON_DAYS,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    sql = LABELED_JOIN_SQL
    params: list[Any] = [int(horizon_days)]
    if max_rows is not None:
        sql += " ORDER BY RANDOM() LIMIT ?"
        params.append(int(max_rows))
    else:
        sql += " ORDER BY o.as_of_date ASC, o.repo_id ASC"
    rows = conn.execute(sql, params).fetchall()
    out: list[dict[str, Any]] = []
    for (
        repo_id,
        as_of_date,
        delta_stars,
        stars,
        forks,
        contributor_count,
        feat_s,
    ) in rows:
        features = extract_snapshot_features(
            stars=stars,
            forks=forks,
            contributor_count=contributor_count,
            features_json=feat_s,
        )
        out.append(
            {
                "repo_id": int(repo_id),
                "as_of_date": str(as_of_date),
                "delta_stars": int(delta_stars),
                "y": 1 if int(delta_stars) > 0 else 0,
                "features": features,
            }
        )
    return out


def train_challenger(
    db_path: Path,
    artifact_dir: Path,
    *,
    cutoff_date: date | None = None,
    memory_limit_mb: int = 384,
) -> dict[str, Any]:
    learn = _import_learn()
    if learn is None:
        return {"status": "skipped", "reason": "sklearn"}
    classifier_cls, accuracy_score, roc_auc_score = learn

    max_rows = MAX_TRAIN_ROWS if memory_limit_mb >= 32 else min(MAX_TRAIN_ROWS, 1000)
    conn = open_readonly(db_path)
    try:
        n_total = _count_labeled(conn)
        rows = load_labeled_rows(
            conn, max_rows=max_rows if n_total > max_rows else None
        )
    finally:
        conn.close()

    n = len(rows)
    if n < MIN_SAMPLES:
        return {"status": "skipped", "reason": "few_samples", "n": n}

    as_of_dates = [date.fromisoformat(row["as_of_date"]) for row in rows]
    cutoff = cutoff_date or (max(as_of_dates) - timedelta(days=30))
    cutoff_s = cutoff.isoformat() if isinstance(cutoff, date) else str(cutoff)
    names = _feature_names(rows)
    train_rows = [row for row in rows if row["as_of_date"] < cutoff_s]
    test_rows = [row for row in rows if row["as_of_date"] >= cutoff_s]
    if not train_rows:
        return {
            "status": "skipped",
            "reason": "empty_train",
            "n": n,
            "cutoff_date": cutoff_s,
        }

    x_train = _to_matrix([row["features"] for row in train_rows], names)
    y_train = [row["y"] for row in train_rows]
    model = classifier_cls(random_state=0, max_iter=80)
    model.fit(x_train, y_train)

    metrics: dict[str, Any] = {
        "n": n,
        "n_train": len(train_rows),
        "n_test": len(test_rows),
        "accuracy": None,
        "auc": None,
    }
    if test_rows:
        x_test = _to_matrix([row["features"] for row in test_rows], names)
        y_test = [row["y"] for row in test_rows]
        pred = list(model.predict(x_test))
        metrics["accuracy"] = float(accuracy_score(y_test, pred))
        metrics["auc"] = _safe_auc(model, x_test, y_test, roc_auc_score)

    trained_at = datetime.now(UTC)
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"challenger-{trained_at.date().isoformat()}.joblib"
    payload = {
        "model": model,
        "feature_names": names,
        "cutoff_date": cutoff_s,
        "trained_at": trained_at.isoformat(),
        "model_type": "HistGradientBoostingClassifier",
        "label": "delta_stars>0",
        "champion": FORMULA_CHAMPION,
    }
    _dump_artifact(payload, artifact_path)
    _insert_model_run(
        db_path,
        name=artifact_path.stem,
        trained_at=trained_at.isoformat(),
        cutoff=cutoff_s,
        metrics=metrics,
        artifact_path=str(artifact_path),
    )
    return {
        "status": "trained",
        "artifact_path": str(artifact_path),
        "n": n,
        "n_train": len(train_rows),
        "n_test": len(test_rows),
        "cutoff_date": cutoff_s,
        "metrics": metrics,
        "champion": FORMULA_CHAMPION,
        "promoted": False,
    }


def evaluate_champion_challenger(
    conn_ro: sqlite3.Connection,
    artifact_path: Path | str,
    cutoff: date,
) -> dict[str, Any]:
    learn = _import_learn()
    if learn is None:
        return {"status": "skipped", "reason": "sklearn"}
    _, accuracy_score, roc_auc_score = learn

    cutoff_s = cutoff.isoformat() if isinstance(cutoff, date) else str(cutoff)
    payload = _load_artifact(Path(artifact_path))
    model = payload["model"]
    names = list(payload["feature_names"])

    rows = conn_ro.execute(
        LABELED_JOIN_SQL
        + """
        AND o.as_of_date >= ?
        ORDER BY o.as_of_date ASC, o.repo_id ASC
        """,
        (TRAIN_HORIZON_DAYS, cutoff_s),
    ).fetchall()
    feature_rows: list[dict[str, float]] = []
    y: list[int] = []
    keys: list[tuple[int, str]] = []
    for (
        repo_id,
        as_of_date,
        delta_stars,
        stars,
        forks,
        contributor_count,
        feat_s,
    ) in rows:
        feature_rows.append(
            extract_snapshot_features(
                stars=stars,
                forks=forks,
                contributor_count=contributor_count,
                features_json=feat_s,
            )
        )
        y.append(1 if int(delta_stars) > 0 else 0)
        keys.append((int(repo_id), str(as_of_date)))

    n_test = len(y)
    challenger: dict[str, Any] = {"accuracy": None, "auc": None, "n": n_test}
    if n_test:
        x_test = _to_matrix(feature_rows, names)
        pred = list(model.predict(x_test))
        challenger["accuracy"] = float(accuracy_score(y, pred))
        challenger["auc"] = _safe_auc(model, x_test, y, roc_auc_score)

    eev_by_key = _formula_eev_map(conn_ro, cutoff_s)
    champ_scores: list[float] = []
    champ_y: list[int] = []
    champ_pred: list[int] = []
    for key, label in zip(keys, y, strict=True):
        eev = eev_by_key.get(key)
        if eev is None:
            continue
        champ_scores.append(float(eev))
        champ_y.append(label)
        champ_pred.append(1 if float(eev) >= CHAMPION_EEV_THRESHOLD else 0)

    if not champ_y:
        champion: dict[str, Any] = {
            "name": FORMULA_CHAMPION,
            "status": "skipped",
            "reason": "intel_scores",
        }
    else:
        champion = {
            "name": FORMULA_CHAMPION,
            "accuracy": float(accuracy_score(champ_y, champ_pred)),
            "auc": _auc_from_scores(champ_y, champ_scores, roc_auc_score),
            "n": len(champ_y),
        }
    return {
        "status": "ok",
        "champion": champion,
        "challenger": challenger,
        "n_test": n_test,
        "cutoff_date": cutoff_s,
    }


def _import_learn() -> tuple[Any, Any, Any] | None:
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.metrics import accuracy_score, roc_auc_score
    except ImportError:
        return None
    return HistGradientBoostingClassifier, accuracy_score, roc_auc_score


def _count_labeled(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM outcome_labels o
        JOIN snapshots s
          ON s.repo_id = o.repo_id
         AND s.snapshot_date = o.as_of_date
        WHERE o.horizon_days = ?
          AND o.delta_stars IS NOT NULL
        """,
        (TRAIN_HORIZON_DAYS,),
    ).fetchone()
    return int(row[0]) if row else 0


def _feature_names(rows: list[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for row in rows:
        keys.update(row["features"])
    return sorted(keys)


def _to_matrix(
    feature_dicts: list[dict[str, float]], names: list[str]
) -> list[list[float]]:
    matrix: list[list[float]] = []
    for feats in feature_dicts:
        row: list[float] = []
        for name in names:
            value = feats.get(name)
            row.append(float(value) if value is not None else float("nan"))
        matrix.append(row)
    return matrix


def _put_numeric(feats: dict[str, float], key: str, value: Any) -> None:
    if key in LEAK_FEATURE_KEYS or value is None:
        return
    if isinstance(value, bool):
        feats[key] = 1.0 if value else 0.0
    elif isinstance(value, (int, float)):
        feats[key] = float(value)


def _parse_features_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _numeric_items(obj: dict[str, Any], prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in obj.items():
        name = f"{prefix}{key}" if prefix else str(key)
        if name in LEAK_FEATURE_KEYS:
            continue
        if isinstance(value, dict):
            nested = name if name.endswith("_") else f"{name}_"
            out.update(_numeric_items(value, nested))
            continue
        if isinstance(value, bool):
            out[name] = 1.0 if value else 0.0
        elif isinstance(value, (int, float)):
            out[name] = float(value)
    return out


def _safe_auc(
    model: Any, x_test: Any, y: list[int], roc_auc_score: Any
) -> float | None:
    if len(set(y)) < 2 or not hasattr(model, "predict_proba"):
        return None
    try:
        proba = model.predict_proba(x_test)
        classes = list(getattr(model, "classes_", []))
        if 1 in classes:
            scores = proba[:, classes.index(1)]
        else:
            scores = proba[:, -1]
    except (ValueError, IndexError, AttributeError):
        return None
    return _auc_from_scores(y, scores, roc_auc_score)


def _auc_from_scores(y: Any, scores: Any, roc_auc_score: Any) -> float | None:
    labels = [int(v) for v in y]
    if len(set(labels)) < 2:
        return None
    try:
        return float(roc_auc_score(labels, scores))
    except ValueError:
        return None


def _dump_artifact(payload: dict[str, Any], path: Path) -> None:
    try:
        import joblib
    except ImportError:
        path.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
        return
    joblib.dump(payload, path)


def _load_artifact(path: Path) -> dict[str, Any]:
    try:
        import joblib
    except ImportError:
        payload = pickle.loads(path.read_bytes())
    else:
        try:
            payload = joblib.load(path)
        except (OSError, ValueError, pickle.UnpicklingError):
            payload = pickle.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise TypeError("challenger artifact must be a dict")
    return payload


def _insert_model_run(
    db_path: Path | str,
    *,
    name: str,
    trained_at: str,
    cutoff: str,
    metrics: dict[str, Any],
    artifact_path: str,
) -> None:
    conn = sqlite3.connect(str(Path(db_path).resolve()))
    try:
        conn.execute(
            """
            INSERT INTO model_runs(
              name, trained_at, train_cutoff_date, metrics_json, artifact_path, status
            ) VALUES (?,?,?,?,?,'trained')
            """,
            (
                name,
                trained_at,
                cutoff,
                json.dumps(metrics, ensure_ascii=False),
                artifact_path,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _formula_eev_map(
    conn: sqlite3.Connection, cutoff_s: str
) -> dict[tuple[int, str], float]:
    try:
        rows = conn.execute(
            """
            SELECT repo_id, as_of_date, score
            FROM intel_scores
            WHERE model_run_id = 1
              AND as_of_date >= ?
              AND score IS NOT NULL
            """,
            (cutoff_s,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {(int(repo_id), str(as_of)): float(score) for repo_id, as_of, score in rows}
