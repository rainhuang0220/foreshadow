from foreshadow.db import connect, migrate
from foreshadow.mission import build_mission, persist_mission, record_event
from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.learning import MIN_OBSERVATIONS, observed_access


def _seed_events(conn, uid, mid, full_name, events: list[str]) -> None:
    for ev in events:
        record_event(
            conn,
            user_id=uid,
            mission_id=mid,
            full_name=full_name,
            event=ev,
        )


def test_observed_access_unknown_is_not_zero(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission("acme/toy", feat=FeaturesBlob(), stars=10, age_days=12, contributors=2)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    _seed_events(conn, uid, mid, "acme/toy", ["entered", "local_setup"])
    out = observed_access(conn, user_id=uid, full_name="acme/toy")
    assert out["score"] is None
    assert out["n"] < MIN_OBSERVATIONS
    assert "not 0" in out["why"].lower() or "不是 0" in out["why"]


def test_observed_access_uses_outcomes_not_formula_weights(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission("acme/open", feat=FeaturesBlob(maint_touch=0.2), stars=80, age_days=40, contributors=6)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    _seed_events(
        conn,
        uid,
        mid,
        "acme/open",
        [
            "maintainer_replied",
            "issue_accepted",
            "pr_reviewed",
            "pr_merged",
        ],
    )
    out = observed_access(conn, user_id=uid, full_name="acme/open")
    assert out["score"] is not None
    assert out["score"] >= 70
    assert out["source"] == "user_events"
    silent = build_mission("acme/silent", feat=FeaturesBlob(), stars=80, age_days=40, contributors=6)
    sid = persist_mission(conn, silent, user_id=uid, repo_id=None)
    _seed_events(
        conn,
        uid,
        sid,
        "acme/silent",
        ["maintainer_silent", "pr_rejected", "maintainer_silent"],
    )
    low = observed_access(conn, user_id=uid, full_name="acme/silent")
    assert low["score"] is not None
    assert low["score"] < out["score"]
