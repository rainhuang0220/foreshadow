from foreshadow.db import connect, migrate
from foreshadow.mission import (
    REMOTE_ACTIONS,
    build_mission,
    persist_mission,
    prepare_local_dir,
    refuse_remote_action,
)
from foreshadow.models import FeaturesBlob


def test_build_mission_waits_for_user():
    m = build_mission(
        "acme/toy",
        feat=FeaturesBlob(bug_n=3, issue_sample_n=6, maint_touch=0.4),
        age_days=40,
        contributors=5,
        stars=80,
        pushed_age_days=1,
    )
    assert m.needs_user_approval is True
    assert m.status == "MISSION_READY"
    assert m.strategy.allows_direct_pr is False
    assert m.strategy.steps_zh


def test_refuse_remote_never_posts():
    for action in REMOTE_ACTIONS:
        out = refuse_remote_action(action)
        assert out["blocked"] is True
        assert out["ok"] is False
        assert "远程" in out["error"]


def test_transition_and_portfolio(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission("acme/toy", feat=FeaturesBlob(gap_docs=1), stars=12, age_days=20, contributors=2)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    from foreshadow.mission import portfolio, record_event, transition

    transition(conn, mid, uid, "LOCAL_SETUP")
    record_event(conn, user_id=uid, mission_id=mid, full_name="acme/toy", event="local_setup")
    port = portfolio(conn, uid)
    assert port["missions"] == 1
    assert port["by_status"].get("LOCAL_SETUP") == 1
    assert port["events"].get("local_setup") == 1


def test_persist_mission(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission("acme/toy", feat=FeaturesBlob(gap_docs=1), stars=20, age_days=30, contributors=3)
    dest = prepare_local_dir(tmp_home, "acme/toy")
    m.local_path = str(dest)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    assert mid >= 1
    assert (dest / "FORESHADOW.md").is_file()
    row = conn.execute("SELECT status, entry_path FROM entry_missions WHERE id=?", (mid,)).fetchone()
    assert row[0] == "MISSION_READY"
    assert row[1] == "DOCUMENTATION"
