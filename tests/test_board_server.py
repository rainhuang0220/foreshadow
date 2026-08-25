from __future__ import annotations

import threading

import httpx
import pytest

from fakes import seed_repo
from foreshadow.board.server import make_server, validate_host
from foreshadow.clock import Clock
from foreshadow.db import connect, migrate
from foreshadow.pipeline.snapshot import upsert_snapshot


def _seed_board(home, clock: Clock) -> None:
    conn = connect(home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "N1", "acme/x")
    upsert_snapshot(
        conn,
        rid,
        "2026-08-24",
        {
            "stars": 120,
            "forks": 11,
            "open_issues": 4,
            "open_prs": 1,
            "last_pushed_at": "2026-08-20T00:00:00Z",
            "created_at": "2026-05-01T00:00:00Z",
            "captured_at": clock.now().isoformat(),
            "topics_json": "[]",
            "features_json": '{"phase":"B","u_issue_ext":8}',
            "completeness": 1.0,
            "contributor_count": 6,
        },
    )
    conn.execute(
        "INSERT INTO daily_runs(run_date, started_at, status, budget_cap) "
        "VALUES ('2026-08-24', ?, 'complete', 800)",
        (clock.now().isoformat(),),
    )
    conn.execute(
        "INSERT INTO candidates(run_id, repo_id, discovery_source, hydrate_status) "
        "VALUES (1, ?, 'search', 'ok')",
        (rid,),
    )
    conn.commit()


def _run_server(tmp_home, frozen_clock):
    _seed_board(tmp_home, frozen_clock)
    httpd = make_server(
        host="127.0.0.1",
        port=0,
        date="2026-08-24",
        preview=True,
        clock=frozen_clock,
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    return httpd, f"http://{host}:{port}"


def test_validate_host_rejects_wildcard():
    with pytest.raises(ValueError, match="回环"):
        validate_host("0.0.0.0")
    assert validate_host("127.0.0.1") == "127.0.0.1"


def test_board_requires_login_then_isolates_reviews(tmp_home, frozen_clock):
    httpd, base = _run_server(tmp_home, frozen_clock)
    try:
        page = httpx.get(f"{base}/")
        assert page.status_code == 200
        assert "今日机会审查" in page.text
        assert "FORESHADOW" in page.text

        anon = httpx.get(f"{base}/api/board")
        assert anon.status_code == 401

        a = httpx.Client()
        reg = a.post(
            f"{base}/api/register",
            json={
                "username": "alice",
                "email": "alice@example.com",
                "password": "password1",
            },
        )
        assert reg.status_code == 200
        assert "password" not in reg.text
        board = a.get(f"{base}/api/board")
        assert board.status_code == 200
        payload = board.json()
        assert payload["mode_zh"] == "预览模式"
        assert payload["candidates"]
        first = payload["candidates"][0]
        assert first["rank"] == 1
        assert "detail" in first
        assert first["detail"]["review_actions"]
        assert first.get("my_action") in (None, "")

        saved = a.post(
            f"{base}/api/review",
            json={"repo": first["full_name"], "action": "interested"},
        )
        assert saved.status_code == 200
        again = a.get(f"{base}/api/board").json()
        mine = next(
            c for c in again["candidates"] if c["full_name"] == first["full_name"]
        )
        assert mine["my_action"] == "interested"

        a.post(f"{base}/api/logout", json={})
        b = httpx.Client()
        reg_b = b.post(
            f"{base}/api/register",
            json={
                "username": "bob",
                "email": "bob@example.com",
                "password": "password1",
            },
        )
        assert reg_b.status_code == 200
        bob_board = b.get(f"{base}/api/board").json()
        bob_card = next(
            c for c in bob_board["candidates"] if c["full_name"] == first["full_name"]
        )
        assert bob_card["my_action"] in (None, "")
        assert "开始进入" in page.text
        assert "row .act" in page.text
        assert "FORESHADOW.md" in page.text
        assert "正在打开今日机会榜" in page.text
        assert "查看任务" in page.text
        assert "暂停扫描" in page.text
        assert "Escape" in page.text
        assert "/api/mission" in page.text
        assert "正在准备本地环境" in page.text
        assert "clone.error" in page.text or "cloneErr" in page.text
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_mission_api_blocks_remote_and_records_event(tmp_home, frozen_clock, monkeypatch):
    monkeypatch.setenv("FORESHADOW_SKIP_CLONE", "1")
    httpd, base = _run_server(tmp_home, frozen_clock)
    try:
        a = httpx.Client()
        reg = a.post(
            f"{base}/api/register",
            json={
                "username": "cara",
                "email": "cara@example.com",
                "password": "password1",
            },
        )
        assert reg.status_code == 200
        created = a.post(f"{base}/api/mission", json={"full_name": "acme/x"})
        assert created.status_code == 200
        mission = created.json()["mission"]
        assert mission["needs_user_approval"] is True
        assert mission["status"] == "MISSION_READY"
        assert mission["strategy"]["allows_direct_pr"] is False
        remote = a.post(
            f"{base}/api/mission/remote", json={"action": "create_pr"}
        )
        assert remote.status_code == 200
        assert remote.json()["blocked"] is True
        setup = a.post(
            f"{base}/api/mission/setup", json={"id": mission["id"]}
        )
        assert setup.status_code == 200
        body = setup.json()
        assert body["clone"]["ok"] is False
        assert body["mission"]["status"] != "SUBMITTED"
        listed = a.get(f"{base}/api/missions").json()
        assert listed["missions"]
        port = a.get(f"{base}/api/portfolio").json()
        assert port["missions"] >= 1
        assert port["observed_access"]["score"] is None
        after = a.get(f"{base}/api/board").json()
        card = next(c for c in after["candidates"] if c["full_name"] == "acme/x")
        assert card.get("mission_id") == mission["id"]
        ev = a.post(
            f"{base}/api/mission/event",
            json={"id": mission["id"], "event": "abandoned"},
        )
        assert ev.status_code == 200
        assert ev.json()["mission"]["status"] == "ABANDONED"
    finally:
        httpd.shutdown()
        httpd.server_close()
