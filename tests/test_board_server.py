from __future__ import annotations

import inspect
import threading

import httpx
import pytest

from fakes import seed_repo
from foreshadow.board.server import _resolve_static, make_server, validate_host
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


def test_board_html_renders_pipeline_states_in_chinese():
    from foreshadow.board.webapp import render_app_html

    html = render_app_html()
    for label in (
        "克隆仓库",
        "创建本地分支",
        "检查仓库",
        "读取 Issue",
        "收集测试",
        "生成草稿",
        "等待确认",
    ):
        assert label in html
    assert 'done:"✓"' in html
    assert 'pending:"○"' in html
    assert 'running:"◐"' in html
    assert 'failed:"✕"' in html
    assert 'skipped:"跳过"' in html
    assert "需要用户授权安装依赖" in html
    assert "已克隆到本机" in html
    assert "stripStepPrefix" in html
    assert "本地 clone 未完成" in html
    assert "Clone done" not in html
    assert "pipelineLive" in html
    assert "LOCAL_SETUP" in html
    js = html[html.index("function renderPipelineStep") : html.index("function progressChecklist")]
    assert "step.label" not in js or "label_zh" in js
    assert "Clone" not in js


def test_board_requires_login_then_isolates_reviews(tmp_home, frozen_clock):
    httpd, base = _run_server(tmp_home, frozen_clock)
    try:
        page = httpx.get(f"{base}/")
        assert page.status_code == 200
        assert "今日机会" in page.text
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
        assert "README：有" in page.text
        assert "正在打开今日机会榜" in page.text
        assert "retryBoard" in page.text
        assert "已知为 0，不是未知" in page.text
        assert "记入观察清单" in page.text
        assert "查看任务" in page.text
        assert "暂停扫描" in page.text
        assert "Escape" in page.text
        assert "/api/mission" in page.text
        assert "正在准备本地环境" in page.text
        assert "clone.error" in page.text or "cloneErr" in page.text
        html = page.text
        start_js = html[
            html.index("async function startEnter") : html.index("async function setupLocal")
        ]
        existing_js = html[
            html.index("async function openExisting") : html.index("async function markEvent")
        ]
        resume_js = html[
            html.index("async function resumeMission") : html.index("async function refuseRemote")
        ]
        assert "await setupLocal" in start_js
        assert "alreadyLocal" in start_js
        assert 'api("/api/mission"' in start_js
        assert "/api/mission/setup" not in start_js
        assert "missionIsOpen" in html
        assert "为什么现在：" in html
        assert "button:disabled" in html
        assert "进入通道：" in html
        assert "setupLocal" not in existing_js
        assert "/api/mission/setup" not in existing_js
        assert 'api("/api/missions"' in existing_js
        assert "setupLocal" not in resume_js
        assert "/api/mission/setup" not in resume_js
        bg = a.get(f"{base}/static/board-bg.jpg")
        assert bg.status_code == 200
        assert "image/jpeg" in bg.headers.get("content-type", "")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_post_api_mission_does_not_clone(tmp_home, frozen_clock, monkeypatch):
    from foreshadow.mission import create_for_user

    assert "clone_public_repo" not in inspect.getsource(create_for_user)
    monkeypatch.delenv("FORESHADOW_SKIP_CLONE", raising=False)

    def explode(*_a, **_k):
        raise AssertionError("POST /api/mission must not invoke clone_public_repo")

    monkeypatch.setattr("foreshadow.mission.clone_public_repo", explode)
    httpd, base = _run_server(tmp_home, frozen_clock)
    try:
        a = httpx.Client()
        reg = a.post(
            f"{base}/api/register",
            json={
                "username": "erin",
                "email": "erin@example.com",
                "password": "password1",
            },
        )
        assert reg.status_code == 200
        created = a.post(f"{base}/api/mission", json={"full_name": "acme/x"})
        assert created.status_code == 200
        mission = created.json()["mission"]
        assert mission["status"] == "MISSION_READY"
        dest = tmp_home / "work" / "acme__x"
        assert (dest / "FORESHADOW.md").is_file()
        assert not (dest / "repo").exists()
        assert not (dest / "repo" / ".git").exists()
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
        dest = tmp_home / "work" / "acme__x"
        assert not (dest / "repo").exists()
        assert not (dest / "repo" / ".git").exists()
        from foreshadow.mission import (
            REMOTE_ACTIONS,
            create_for_user,
            refuse_remote_action,
        )

        assert "clone_public_repo" not in inspect.getsource(create_for_user)

        for action in sorted(REMOTE_ACTIONS):
            remote = a.post(
                f"{base}/api/mission/remote", json={"action": action}
            )
            assert remote.status_code == 200
            assert remote.json() == refuse_remote_action(action)
        anon = httpx.Client()
        guest = anon.post(
            f"{base}/api/mission/remote", json={"action": "push_branch"}
        )
        assert guest.status_code == 200
        assert guest.json() == refuse_remote_action("push_branch")
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
        spoof = a.post(
            f"{base}/api/mission/event",
            json={"id": mission["id"], "event": "user_submitted"},
        )
        assert spoof.status_code == 200
        assert spoof.json()["mission"]["status"] != "SUBMITTED"
        listed_zh = a.get(f"{base}/api/missions").json()["missions"]
        assert listed_zh[0].get("status_zh")
        ev = a.post(
            f"{base}/api/mission/event",
            json={"id": mission["id"], "event": "abandoned"},
        )
        assert ev.status_code == 200
        assert ev.json()["mission"]["status"] == "ABANDONED"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_resolve_static_serves_assets_only(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "board-bg.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    (assets / "board-bg.png").write_bytes(b"png")
    (assets / "board-bg.webp").write_bytes(b"webp")
    (tmp_path / "secret.jpg").write_bytes(b"nope")
    monkeypatch.setattr("foreshadow.board.server._ASSETS_DIR", assets)

    jpg = _resolve_static("/static/board-bg.jpg")
    png = _resolve_static("/static/board-bg.png")
    webp = _resolve_static("/static/board-bg.webp")
    assert jpg is not None
    assert png is not None
    assert webp is not None
    assert jpg[1] == "image/jpeg"
    assert jpg[0].read_bytes() == b"\xff\xd8\xff\xd9"
    assert png[1] == "image/png"
    assert webp[1] == "image/webp"
    assert _resolve_static("/static/../secret.jpg") is None
    assert _resolve_static("/static/%2e%2e/secret.jpg") is None
    assert _resolve_static("/static/%2e%2e%2fsecret.jpg") is None
    assert _resolve_static("/static/foo/board-bg.jpg") is None
    assert _resolve_static("/static/missing.png") is None
    assert _resolve_static("/static/") is None


def test_static_board_bg_and_login_get(tmp_home, frozen_clock):
    httpd, base = _run_server(tmp_home, frozen_clock)
    try:
        page = httpx.get(f"{base}/")
        assert page.status_code == 200
        bg = httpx.get(f"{base}/static/board-bg.jpg")
        assert bg.status_code == 200
        assert "image/jpeg" in bg.headers.get("content-type", "")
        missing = httpx.get(f"{base}/static/no-such.webp")
        assert missing.status_code == 404
        assert missing.status_code != 500
        client = httpx.Client()
        reg = client.post(
            f"{base}/api/register",
            json={
                "username": "dana",
                "email": "dana@example.com",
                "password": "password1",
            },
        )
        assert reg.status_code == 200
        after = client.get(f"{base}/")
        assert after.status_code == 200
        board = client.get(f"{base}/api/board")
        assert board.status_code == 200
        still = client.get(f"{base}/static/board-bg.jpg")
        assert still.status_code == 200
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_p0_view_enter_remote_and_official_gates():
    from foreshadow.board.server import BoardHandler
    from foreshadow.board.webapp import render_app_html
    from foreshadow.mission import create_for_user, refuse_remote_action, setup_local_environment
    from foreshadow.pipeline.select import is_official_eligible, select_top

    assert "clone_public_repo" not in inspect.getsource(create_for_user)
    assert "setup_local_environment" not in inspect.getsource(create_for_user)
    assert "clone_public_repo" in inspect.getsource(setup_local_environment)

    html = render_app_html()
    start_js = html[
        html.index("async function startEnter") : html.index("async function setupLocal")
    ]
    existing_js = html[
        html.index("async function openExisting") : html.index("async function markEvent")
    ]
    assert "await setupLocal" in start_js
    assert 'api("/api/mission"' in start_js
    assert "/api/mission/setup" not in start_js
    assert "setupLocal" not in existing_js
    assert "/api/mission/setup" not in existing_js

    post_src = inspect.getsource(BoardHandler.do_POST)
    remote = post_src[post_src.index("/api/mission/remote") :]
    assert "refuse_remote_action" in remote
    assert "clone_public_repo" not in remote
    blocked = refuse_remote_action("create_pr")
    assert blocked["ok"] is False
    assert blocked["blocked"] is True

    for fn in (select_top, is_official_eligible):
        params = inspect.signature(fn).parameters
        assert params["min_opportunity"].default == 55
        assert params["min_explosion"].default == 35
