import json

from fakes import FakeGitHub, seed_repo
from foreshadow.db import connect, migrate
from foreshadow.pipeline.access_sample import sample_medium_access
from foreshadow.pipeline.snapshot import upsert_snapshot


def test_sample_medium_access_fills_pr_fields(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_m", "acme/medium")
    upsert_snapshot(
        conn,
        rid,
        "2026-08-25",
        {
            "stars": 80,
            "forks": 2,
            "open_issues": 1,
            "open_prs": 0,
            "last_pushed_at": "2026-08-20T00:00:00Z",
            "created_at": "2026-05-01T00:00:00Z",
            "captured_at": frozen_clock.now().isoformat(),
            "topics_json": "[]",
            "features_json": '{"phase":"M","commits_7d":4}',
            "completeness": 1.0,
            "contributor_count": 3,
        },
    )
    conn.commit()
    gh = FakeGitHub(
        pulls={
            "acme/medium": [
                {
                    "merged_at": "2026-08-01T00:00:00Z",
                    "author_association": "CONTRIBUTOR",
                },
                {"merged_at": "2026-08-02T00:00:00Z", "author_association": "OWNER"},
                {"merged_at": None, "author_association": "CONTRIBUTOR"},
            ]
        }
    )
    out = sample_medium_access(conn, gh, limit=10)
    assert out["updated"] == 1
    feat = json.loads(
        conn.execute(
            "SELECT features_json FROM snapshots WHERE repo_id=?", (rid,)
        ).fetchone()[0]
    )
    assert feat["phase"] == "M"
    assert feat["pr_merged_sample_n"] == 2
    assert feat["pr_external_merged_n"] == 1
    assert feat["pr_accept_rate"] == 0.5
    assert feat["pr_review_rate"] is None
    assert feat["commits_7d"] == 4


def test_sample_medium_skips_phase_b(tmp_home, frozen_clock):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_b", "acme/deep")
    upsert_snapshot(
        conn,
        rid,
        "2026-08-25",
        {
            "stars": 80,
            "forks": 2,
            "open_issues": 1,
            "open_prs": 0,
            "last_pushed_at": "2026-08-20T00:00:00Z",
            "created_at": "2026-05-01T00:00:00Z",
            "captured_at": frozen_clock.now().isoformat(),
            "topics_json": "[]",
            "features_json": '{"phase":"B","pr_merged_sample_n":8,"pr_accept_rate":0.4}',
            "completeness": 1.0,
            "contributor_count": 3,
        },
    )
    conn.commit()
    gh = FakeGitHub(pulls={"acme/deep": [{"merged_at": "2026-08-01T00:00:00Z"}]})
    out = sample_medium_access(conn, gh, limit=10)
    assert out["updated"] == 0
    feat = json.loads(
        conn.execute(
            "SELECT features_json FROM snapshots WHERE repo_id=?", (rid,)
        ).fetchone()[0]
    )
    assert feat["pr_merged_sample_n"] == 8
