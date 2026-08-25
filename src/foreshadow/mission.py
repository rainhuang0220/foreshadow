"""Entry Mission: local plan + optional clone. Never posts to GitHub."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.access import compute_access
from foreshadow.pipeline.activity import compute_activity
from foreshadow.pipeline.s1 import compute_s1
from foreshadow.pipeline.strategy import StrategyResult, recommend_entry

Status = Literal[
    "DISCOVERED",
    "INTERESTED",
    "INVESTIGATING",
    "MISSION_READY",
    "LOCAL_SETUP",
    "REPRODUCING",
    "DISCUSSING",
    "IMPLEMENTING",
    "DRAFT_READY",
    "WAITING_USER_APPROVAL",
    "SUBMITTED",
    "REVIEWING",
    "MERGED",
    "FOLLOW_UP",
    "ABANDONED",
    "BLOCKED",
    "WAITING_MAINTAINER",
]

REMOTE_ACTIONS = frozenset(
    {"post_issue", "post_discussion", "push_branch", "create_pr", "comment", "review", "merge"}
)
USER_EVENTS = frozenset(
    {
        "entered",
        "local_setup",
        "clone_ok",
        "clone_failed",
        "maintainer_replied",
        "maintainer_silent",
        "issue_accepted",
        "pr_reviewed",
        "pr_merged",
        "pr_rejected",
        "user_submitted",
        "abandoned",
        "draft_approved",
    }
)
REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ISSUE_NUM_RE = re.compile(r"#(\d+)")
CLONE_TIMEOUT_S = 120


@dataclass
class Mission:
    full_name: str
    status: Status
    strategy: StrategyResult
    stage: str | None
    earlyness: float | None
    evidence: float | None
    window: float | None
    access: float | None
    why_now: list[str]
    needs_user_approval: bool
    local_path: str | None = None
    id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "status": self.status,
            "strategy": self.strategy.as_dict(),
            "stage": self.stage,
            "earlyness": self.earlyness,
            "evidence": self.evidence,
            "opportunity_window": self.window,
            "access": self.access,
            "why_now": list(self.why_now),
            "steps_zh": list(self.strategy.steps_zh),
            "difficulty": self.strategy.difficulty,
            "effort": self.strategy.effort,
            "needs_user_approval": self.needs_user_approval,
            "local_path": self.local_path,
            "next_step_zh": next_step_zh(self.status),
            "status_zh": status_zh(self.status),
            "git_ops_zh": [
                "git clone --depth 1（仅本地）",
                "本地分支 foreshadow/entry（不 push）",
                "可本地 commit",
                "不会 push / 开 Issue / 开 PR",
            ],
            "remote_blocked": (
                "等待你的确认才能执行任何远程 GitHub 操作。"
            ),
        }


def build_mission(
    full_name: str,
    *,
    feat: FeaturesBlob | None = None,
    age_days: float | None = None,
    contributors: int | None = None,
    stars: float | None = None,
    pushed_age_days: int | None = None,
    unique_issue_authors: int | None = None,
    language: str | None = None,
) -> Mission:
    feat = feat or FeaturesBlob()
    act = compute_activity(feat)
    acc = compute_access(feat)
    s1 = compute_s1(
        age_days=age_days,
        contributors=contributors,
        stars=stars,
        pushed_age_days=pushed_age_days,
        unique_issue_authors=unique_issue_authors,
        feat=feat,
        activity=act,
    )
    strat = recommend_entry(feat, s1=s1, access=acc, language=language)
    why = [
        f"阶段 {s1.stage}",
        *s1.earlyness_plus[:2],
        *s1.evidence_plus[:2],
        *strat.why,
    ]
    return Mission(
        full_name=full_name,
        status="MISSION_READY",
        strategy=strat,
        stage=s1.stage,
        earlyness=s1.earlyness,
        evidence=s1.evidence,
        window=s1.window,
        access=acc.score,
        why_now=[w for w in why if w],
        needs_user_approval=True,
    )


def persist_mission(
    conn: sqlite3.Connection,
    mission: Mission,
    *,
    user_id: int,
    repo_id: int | None,
) -> int:
    now = datetime.now(UTC).isoformat()
    cur = conn.execute(
        """
        INSERT INTO entry_missions(
          user_id, repo_id, full_name, status, entry_path, difficulty, effort,
          plan_json, local_path, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            repo_id,
            mission.full_name,
            mission.status,
            mission.strategy.path,
            mission.strategy.difficulty,
            mission.strategy.effort,
            json.dumps(mission.as_dict(), ensure_ascii=False),
            mission.local_path,
            now,
            now,
        ),
    )
    conn.commit()
    mission.id = int(cur.lastrowid)
    if mission.local_path:
        write_mission_doc(Path(mission.local_path), mission)
    return mission.id


def list_missions(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, full_name, status, entry_path, difficulty, effort, plan_json,
               local_path, created_at, updated_at
        FROM entry_missions WHERE user_id=? ORDER BY id DESC
        """,
        (user_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            plan = json.loads(row[6] or "{}")
        except json.JSONDecodeError:
            plan = {}
        plan.update(
            {
                "id": row[0],
                "full_name": row[1],
                "status": row[2],
                "status_zh": status_zh(str(row[2])),
                "next_step_zh": next_step_zh(str(row[2])),
                "needs_user_approval": True,
                "local_path": row[7],
                "created_at": row[8],
                "updated_at": row[9],
            }
        )
        out.append(plan)
    return out


def set_status(
    conn: sqlite3.Connection, mission_id: int, user_id: int, status: Status
) -> None:
    conn.execute(
        """
        UPDATE entry_missions SET status=?, updated_at=?
        WHERE id=? AND user_id=?
        """,
        (status, datetime.now(UTC).isoformat(), mission_id, user_id),
    )
    conn.commit()


def create_for_user(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    full_name: str,
    data_dir: Path,
) -> Mission:
    from foreshadow.pipeline import load_score_input

    existing = conn.execute(
        """
        SELECT id FROM entry_missions
        WHERE user_id=? AND full_name=?
          AND status NOT IN ('ABANDONED', 'MERGED')
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, full_name),
    ).fetchone()
    if existing:
        plan = load_mission_plan(conn, int(existing[0]), user_id)
        if plan is not None:
            return mission_from_plan(plan)

    row = conn.execute(
        "SELECT id FROM repos WHERE full_name=?", (full_name,)
    ).fetchone()
    repo_id = int(row[0]) if row else None
    data = load_score_input(conn, repo_id) if repo_id is not None else None
    feat = FeaturesBlob()
    age = None
    pushed = None
    stars = None
    contrib = None
    u_issue = None
    if data:
        raw = data.get("features") or {}
        if isinstance(raw, dict):
            feat = FeaturesBlob.model_validate(raw)
        stars = data.get("S")
        contrib = data.get("C")
        u_issue = data.get("U_issue") or feat.u_issue
        age = data.get("age_days")
        pushed = data.get("pushed_age_days")
        if age is None:
            from foreshadow.pipeline.hydrate import parse_dt

            created = parse_dt(data.get("created_at"))
            if created is not None:
                age = max((datetime.now(UTC).date() - created.date()).days, 1)
        if pushed is None:
            from foreshadow.pipeline.hydrate import parse_dt

            p = parse_dt(data.get("pushed_at"))
            if p is not None:
                pushed = max((datetime.now(UTC).date() - p.date()).days, 0)
    language = None
    if data and data.get("language"):
        language = str(data.get("language"))
    mission = build_mission(
        full_name,
        feat=feat,
        age_days=age,
        contributors=contrib,
        stars=stars,
        pushed_age_days=pushed,
        unique_issue_authors=u_issue,
        language=language,
    )
    dest = prepare_local_dir(data_dir, full_name)
    mission.local_path = str(dest)
    write_mission_doc(dest, mission)
    persist_mission(conn, mission, user_id=user_id, repo_id=repo_id)
    record_event(
        conn,
        user_id=user_id,
        mission_id=mission.id,
        full_name=full_name,
        event="entered",
        detail={"path": mission.strategy.path},
    )
    return mission


ALLOWED = {
    "MISSION_READY": {"LOCAL_SETUP", "INVESTIGATING", "ABANDONED"},
    "LOCAL_SETUP": {"WAITING_USER_APPROVAL", "DRAFT_READY", "ABANDONED", "BLOCKED"},
    "WAITING_USER_APPROVAL": {
        "ABANDONED",
        "BLOCKED",
        "WAITING_MAINTAINER",
        "DRAFT_READY",
        "IMPLEMENTING",
    },
    "DRAFT_READY": {"WAITING_USER_APPROVAL", "ABANDONED"},
    "INVESTIGATING": {"MISSION_READY", "ABANDONED"},
    "IMPLEMENTING": {"DRAFT_READY", "WAITING_USER_APPROVAL", "ABANDONED", "BLOCKED"},
    "WAITING_MAINTAINER": {"FOLLOW_UP", "ABANDONED", "BLOCKED", "REVIEWING"},
    "REVIEWING": {"FOLLOW_UP", "MERGED", "ABANDONED", "BLOCKED"},
    "FOLLOW_UP": {"ABANDONED", "MERGED"},
}


def transition(
    conn: sqlite3.Connection, mission_id: int, user_id: int, dest: Status
) -> Status:
    row = conn.execute(
        "SELECT status FROM entry_missions WHERE id=? AND user_id=?",
        (mission_id, user_id),
    ).fetchone()
    if row is None:
        raise ValueError("mission not found")
    cur = str(row[0])
    if dest not in ALLOWED.get(cur, set()):
        raise ValueError(f"cannot {cur} -> {dest}")
    set_status(conn, mission_id, user_id, dest)
    return dest


def record_event(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    mission_id: int | None,
    full_name: str,
    event: str,
    detail: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO contribution_events(
          user_id, mission_id, full_name, event, detail_json, created_at
        ) VALUES (?,?,?,?,?,?)
        """,
        (
            user_id,
            mission_id,
            full_name,
            event,
            json.dumps(detail or {}, ensure_ascii=False),
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()


def portfolio(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    missions = list_missions(conn, user_id)
    by_status: dict[str, int] = {}
    for row in missions:
        st = str(row.get("status") or "")
        by_status[st] = by_status.get(st, 0) + 1
    ev = conn.execute(
        "SELECT event, COUNT(*) FROM contribution_events WHERE user_id=? GROUP BY 1",
        (user_id,),
    ).fetchall()
    return {
        "missions": len(missions),
        "by_status": by_status,
        "events": {str(k): int(v) for k, v in ev},
        "entered": by_status.get("MISSION_READY", 0)
        + by_status.get("LOCAL_SETUP", 0)
        + by_status.get("WAITING_USER_APPROVAL", 0),
        "merged": by_status.get("MERGED", 0),
        "note": "Portfolio tracks our missions. It does not scrape third-party GitHub.",
    }


def refuse_remote_action(action: str) -> dict[str, Any]:
    return {
        "ok": False,
        "blocked": True,
        "action": action,
        "error": "远程 GitHub 操作需要你明确批准，Foreshadow 不会自动发送。",
        "status": "WAITING_USER_APPROVAL",
    }


def status_zh(status: str | None) -> str:
    return {
        "MISSION_READY": "任务已就绪",
        "LOCAL_SETUP": "正在准备本地环境",
        "WAITING_USER_APPROVAL": "等待你确认远程操作",
        "DRAFT_READY": "本地草稿已好",
        "IMPLEMENTING": "本地实现中",
        "WAITING_MAINTAINER": "等待维护者",
        "REVIEWING": "按反馈修改",
        "SUBMITTED": "你已自行提交",
        "MERGED": "已合并，可继续跟进",
        "FOLLOW_UP": "后续跟进",
        "ABANDONED": "已停止",
        "BLOCKED": "被拦住",
        "INVESTIGATING": "还在阅读项目",
    }.get(status or "", status or "—")


def next_step_zh(status: str | None) -> str:
    return {
        "MISSION_READY": "准备本地环境（clone / 读文档），不要发 Issue 或 PR",
        "LOCAL_SETUP": "看本地仓库与第一步，确认后再决定是否沟通",
        "WAITING_USER_APPROVAL": "等待你的确认才能执行任何远程 GitHub 操作",
        "DRAFT_READY": "草稿已在本地。远程发送仍需你确认",
        "IMPLEMENTING": "在本地实现最小改动，不要 push",
        "WAITING_MAINTAINER": "等待维护者。不要反复催促或自动评论",
        "REVIEWING": "按反馈改本地补丁，再请你确认是否提交",
        "SUBMITTED": "你已自行提交。Foreshadow 没有代发",
        "MERGED": "记录后续跟进，而不是结束贡献",
        "FOLLOW_UP": "看维护者的下一步，决定是否继续",
        "ABANDONED": "任务已停止",
        "BLOCKED": "被拦住了。先看原因，不要强行发 PR",
        "INVESTIGATING": "继续阅读项目，再生成更具体的入口",
    }.get(status or "", "先阅读推荐入口，再决定")


def prepare_local_dir(root: Path, full_name: str) -> Path:
    safe = _safe_repo_dir(full_name)
    dest = Path(root) / "work" / safe
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def write_mission_doc(dest: Path, mission: Mission, extra: dict[str, Any] | None = None) -> Path:
    extra = extra or {}
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(mission.strategy.steps_zh, 1))
    why = "\n".join(f"- {w}" for w in mission.why_now)
    clone = extra.get("clone") or {}
    inspect = extra.get("inspect") or {}
    text = (
        f"# FORESHADOW ENTRY MISSION\n\n"
        f"项目：{mission.full_name}\n\n"
        f"为什么现在进入：\n{why or '- （待补充）'}\n\n"
        f"阶段：{mission.stage or '—'}\n"
        f"机会窗口：{mission.window}\n"
        f"进入通道：{mission.access}\n"
        f"推荐入口：{mission.strategy.summary_zh}（{mission.strategy.path}）\n"
        f"难度：{mission.strategy.difficulty}\n"
        f"预计：{mission.strategy.effort}\n"
        f"状态：{mission.status}\n"
        f"下一步：{next_step_zh(mission.status)}\n\n"
        f"行动计划：\n{steps}\n\n"
        f"本地 clone：{clone.get('status') or '尚未尝试'}\n"
        f"README：{'有' if inspect.get('has_readme') else '未知'} · "
        f"CONTRIBUTING：{'有' if inspect.get('has_contributing') else '未知'}\n"
        f"仓库顶层：{', '.join(inspect.get('top_entries') or []) or '未知'}\n"
        f"README 目录：{'；'.join(inspect.get('readme_headings') or []) or '未知'}\n"
        f"CONTRIBUTING 目录：{'；'.join(inspect.get('contributing_headings') or []) or '未知'}\n"
    )
    cited = extra.get("cited_issue") or {}
    if cited.get("number"):
        text += (
            f"\n引用 Issue #{cited['number']}：{cited.get('title') or ''}\n"
            f"{(cited.get('body') or '')[:400]}\n"
        )
    text += (
        "\n"
        "成功标准：完成推荐入口的第一步，并等你确认后才向 GitHub 发任何内容。\n\n"
        "同目录还有 ISSUE_DRAFT.md（本地草稿，未发送）。\n"
        "本目录只做本地准备。不会自动 push / 开 Issue / 开 PR。\n"
        "等待你的确认才能执行任何远程 GitHub 操作。\n"
    )
    path = dest / "FORESHADOW.md"
    path.write_text(text, encoding="utf-8")
    return path


def _safe_repo_dir(full_name: str) -> str:
    return full_name.replace("/", "__").replace("..", "")


def github_clone_url(full_name: str) -> str:
    name = (full_name or "").strip()
    if not REPO_NAME_RE.match(name) or ".." in name or name.endswith(".git"):
        raise ValueError("invalid repo name")
    return f"https://github.com/{name}.git"


def clone_public_repo(
    full_name: str,
    dest: Path,
    *,
    runner: Any | None = None,
    timeout: int = CLONE_TIMEOUT_S,
) -> dict[str, Any]:
    """Local `git clone --depth 1` only. Never push. Fail-soft."""
    try:
        url = github_clone_url(full_name)
    except ValueError as exc:
        return {"ok": False, "status": "invalid", "error": str(exc), "path": None}
    clone_dir = Path(dest) / "repo"
    if (clone_dir / ".git").exists():
        return {"ok": True, "status": "exists", "path": str(clone_dir), "error": None}
    if runner is None and os.environ.get("FORESHADOW_SKIP_CLONE") == "1":
        return {
            "ok": False,
            "status": "skipped",
            "error": "clone skipped",
            "path": None,
        }
    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    run = runner or subprocess.run
    cmd = ["git", "clone", "--depth", "1", "--", url, str(clone_dir)]
    try:
        completed = run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=_git_env(),
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "status": "no_git",
            "error": "本机没有 git，已跳过 clone",
            "path": None,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "error": "clone timed out", "path": None}
    code = getattr(completed, "returncode", 1)
    if code != 0:
        err = (getattr(completed, "stderr", None) or getattr(completed, "stdout", None) or "")[
            :400
        ]
        return {"ok": False, "status": "failed", "error": err or "clone failed", "path": None}
    return {"ok": True, "status": "cloned", "path": str(clone_dir), "error": None}


def inspect_clone(clone_dir: Path | None) -> dict[str, Any]:
    if clone_dir is None or not Path(clone_dir).is_dir():
        return {"has_readme": False, "has_contributing": False, "has_tests": False}
    entries = list(Path(clone_dir).iterdir())
    names = {p.name.lower() for p in entries}
    top = sorted(p.name for p in entries)[:20]
    readme = next(
        (p for p in entries if p.is_file() and p.name.lower().startswith("readme")),
        None,
    )
    contrib = next(
        (p for p in entries if p.is_file() and p.name.lower() == "contributing.md"),
        None,
    )
    headings = _markdown_headings(readme) if readme else []
    contrib_headings = _markdown_headings(contrib) if contrib else []
    return {
        "has_readme": any(n.startswith("readme") for n in names),
        "has_contributing": "contributing.md" in names,
        "has_tests": bool({"tests", "test", "spec"} & names),
        "top_entries": top,
        "readme_headings": headings[:12],
        "contributing_headings": contrib_headings[:8],
    }


def _markdown_headings(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:8000]
    except OSError:
        return []
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") and not s.startswith("#!"):
            title = s.lstrip("#").strip()
            if title:
                out.append(title)
    return out


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    for key in ("GITHUB_TOKEN", "GH_TOKEN", "GH_ENTERPRISE_TOKEN"):
        env.pop(key, None)
    return env


ENTRY_BRANCH = "foreshadow/entry"


def refuse_unsafe_local_cmd(cmd: list[str] | str) -> dict[str, Any] | None:
    """Block installers and downloaders. Return None if argv is allowed."""
    parts = list(cmd) if isinstance(cmd, list) else str(cmd).split()
    argv0 = Path(parts[0]).name.lower() if parts else ""
    text = " ".join(parts).lower()
    blocked = {
        "make",
        "cmake",
        "cargo",
        "curl",
        "wget",
        "npm",
        "yarn",
        "pnpm",
        "bun",
        "docker",
        "tox",
        "nox",
    }
    if argv0 in blocked:
        return {"ok": False, "status": "blocked", "error": f"refused {argv0}"}
    needles = (
        "pip install",
        "python -m pip",
        "npm install",
        "yarn ",
        "cargo fetch",
        "cargo test",
        "curl ",
        "| sh",
        "| bash",
    )
    if any(n in text for n in needles):
        return {"ok": False, "status": "blocked", "error": f"refused {text[:80]}"}
    if "push" in parts or "-u" in parts or "--set-upstream" in parts:
        return {"ok": False, "status": "blocked", "error": "refused git push"}
    return None


def create_local_branch(
    clone_dir: Path,
    *,
    runner: Any | None = None,
    name: str = ENTRY_BRANCH,
) -> dict[str, Any]:
    """Local branch only. Idempotent. Never push, never -B reset."""
    root = Path(clone_dir)
    if not (root / ".git").exists():
        return {"ok": False, "status": "no_repo", "name": name, "error": "no clone"}
    run = runner or subprocess.run

    def git(*args: str) -> Any:
        cmd = ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *args]
        blocked = refuse_unsafe_local_cmd(cmd)
        if blocked is not None:
            return SimpleNamespace(returncode=1, stdout="", stderr=blocked["error"])
        return run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=_git_env(),
        )

    try:
        exists = git("show-ref", "--verify", "--quiet", f"refs/heads/{name}")
        if getattr(exists, "returncode", 1) == 0:
            completed = git("checkout", name)
            status = "exists"
        else:
            completed = git("checkout", "-b", name)
            status = "created"
    except FileNotFoundError:
        return {"ok": False, "status": "no_git", "name": name, "error": "本机没有 git"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "name": name, "error": "branch timed out"}
    if getattr(completed, "returncode", 1) != 0:
        err = (getattr(completed, "stderr", None) or "")[:300]
        return {"ok": False, "status": "failed", "name": name, "error": err or "checkout failed"}
    return {"ok": True, "status": status, "name": name, "error": None}


def detect_local_tests(clone_dir: Path) -> dict[str, Any]:
    root = Path(clone_dir)
    if not root.is_dir():
        return {"kind": "none", "reason": "no_repo"}
    names = {p.name.lower() for p in root.iterdir()}
    py = (
        (root / "pyproject.toml").exists()
        or (root / "pytest.ini").exists()
        or (root / "tests").is_dir()
    )
    if "package.json" in names and not py:
        return {"kind": "node", "reason": "npm_test_blocked"}
    if "cargo.toml" in names and not py:
        return {"kind": "cargo", "reason": "cargo_blocked"}
    if py:
        return {"kind": "pytest", "reason": "pytest"}
    return {"kind": "none", "reason": "none"}


def run_local_tests(
    clone_dir: Path,
    *,
    runner: Any | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Allowlisted python -m pytest only. Default collect-only. No installs."""
    import sys

    detected = detect_local_tests(clone_dir)
    if detected["kind"] != "pytest":
        return {
            "ok": False,
            "status": "skipped",
            "kind": detected["kind"],
            "reason": detected["reason"],
        }
    if os.environ.get("FORESHADOW_SKIP_TESTS") == "1":
        return {"ok": False, "status": "skipped", "kind": "pytest", "reason": "skipped"}
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=no", "--maxfail=1"]
    if not execute:
        cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
    blocked = refuse_unsafe_local_cmd(cmd)
    if blocked is not None:
        return blocked
    run = runner or subprocess.run
    try:
        completed = run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=str(clone_dir),
            env=_git_env(),
        )
    except FileNotFoundError:
        return {"ok": False, "status": "no_runner", "kind": "pytest"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "kind": "pytest"}
    code = getattr(completed, "returncode", 1)
    summary = (getattr(completed, "stdout", None) or "")[:400]
    if execute:
        status = "passed" if code == 0 else "failed"
    else:
        status = "collect_ok" if code == 0 else "collect_failed"
    return {
        "ok": code == 0,
        "status": status,
        "kind": "pytest",
        "summary": summary or None,
    }


def probe_python_tests(
    clone_dir: Path,
    *,
    runner: Any | None = None,
) -> dict[str, Any]:
    return run_local_tests(clone_dir, runner=runner, execute=False)


def write_fork_note(dest: Path, full_name: str) -> Path:
    path = Path(dest) / "FORK.md"
    path.write_text(
        f"# Fork 只在你确认以后\n\n"
        f"上游：https://github.com/{full_name}\n\n"
        "若要提交补丁，需要你自己的 fork。Foreshadow **不会**：\n"
        "- 调用 GitHub fork API\n"
        "- 改你的 git remote\n"
        "- push 到 origin\n\n"
        "本地已经 `git clone --depth 1` 到 `repo/`，分支 `foreshadow/entry`。\n"
        "等待你的确认才能执行任何远程 GitHub 操作。\n",
        encoding="utf-8",
    )
    return path


def _draft_title(mission: Mission) -> str:
    for line in [*mission.why_now, *mission.strategy.why]:
        if "建议先看：" in line:
            return line.split("建议先看：", 1)[1].strip()
    return f"{mission.full_name}: {mission.strategy.summary_zh}"


def write_issue_draft(
    dest: Path,
    mission: Mission,
    cited: dict[str, Any] | None = None,
) -> Path:
    path = Path(dest) / "ISSUE_DRAFT.md"
    why = "\n".join(f"- {w}" for w in mission.why_now) or "- （待补充）"
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(mission.strategy.steps_zh, 1))
    kind = {
        "DISCUSSION": "讨论草稿（不要当成 Issue 乱发）",
        "REPRODUCTION": "复现说明草稿",
        "DOCUMENTATION": "文档缺口说明草稿",
        "TEST": "测试缺口说明草稿",
        "TOOLING": "工具链说明草稿（先讨论）",
        "BUG_FIX": "Bug 说明草稿（先沟通，不是 PR）",
        "FEATURE": "功能范围草稿（先 Issue）",
        "BENCHMARK": "测量说明草稿",
        "PERFORMANCE": "性能问题草稿（先数字）",
        "INTEGRATION": "集成方案讨论草稿",
        "RESEARCH": "调研提问草稿",
    }.get(mission.strategy.path, "Issue 草稿")
    cited = cited or {}
    issue_block = ""
    if cited.get("number"):
        issue_block = (
            f"针对：#{cited['number']} {cited.get('title') or ''}\n"
            f"{(cited.get('body') or '')[:600]}\n\n"
        )
    path.write_text(
        f"# {kind}\n\n"
        f"项目：{mission.full_name}\n"
        f"标题：{_draft_title(mission)}\n\n"
        f"{issue_block}"
        f"## 为什么写这份草稿\n{why}\n\n"
        f"## 建议怎么说\n{steps}\n\n"
        "这只是本地草稿，不是 Pull Request。\n"
        "等待你的确认才能发到 GitHub。\n"
        "Foreshadow 不会自动 post Issue / Discussion / PR。\n",
        encoding="utf-8",
    )
    return path


def mission_from_plan(plan: dict[str, Any]) -> Mission:
    from foreshadow.pipeline.strategy import StrategyResult

    raw = plan.get("strategy") if isinstance(plan.get("strategy"), dict) else {}
    strat = StrategyResult(
        path=raw.get("path") or plan.get("entry_path") or "ISSUE",
        summary_zh=raw.get("summary_zh") or "",
        steps_zh=list(raw.get("steps_zh") or plan.get("steps_zh") or []),
        difficulty=raw.get("difficulty") or plan.get("difficulty") or "Medium",
        effort=raw.get("effort") or plan.get("effort") or "6h",
        allows_direct_pr=bool(raw.get("allows_direct_pr")),
        why=list(raw.get("why") or []),
    )
    return Mission(
        full_name=str(plan.get("full_name") or ""),
        status=plan.get("status") or "MISSION_READY",  # type: ignore[arg-type]
        strategy=strat,
        stage=plan.get("stage"),
        earlyness=plan.get("earlyness"),
        evidence=plan.get("evidence"),
        window=plan.get("opportunity_window"),
        access=plan.get("access"),
        why_now=list(plan.get("why_now") or []),
        needs_user_approval=True,
        local_path=plan.get("local_path"),
        id=plan.get("id"),
    )


def load_mission_plan(
    conn: sqlite3.Connection, mission_id: int, user_id: int
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, full_name, status, entry_path, difficulty, effort, plan_json,
               local_path, created_at, updated_at
        FROM entry_missions WHERE id=? AND user_id=?
        """,
        (mission_id, user_id),
    ).fetchone()
    if row is None:
        return None
    try:
        plan = json.loads(row[6] or "{}")
    except json.JSONDecodeError:
        plan = {}
    plan.update(
        {
            "id": row[0],
            "full_name": row[1],
            "status": row[2],
            "local_path": row[7],
            "created_at": row[8],
            "updated_at": row[9],
            "needs_user_approval": True,
            "remote_blocked": "等待你的确认才能执行任何远程 GitHub 操作。",
            "next_step_zh": next_step_zh(str(row[2])),
            "status_zh": status_zh(str(row[2])),
        }
    )
    return plan


def patch_mission_plan(
    conn: sqlite3.Connection,
    mission_id: int,
    user_id: int,
    patch: dict[str, Any],
    *,
    status: Status | None = None,
    local_path: str | None = None,
) -> dict[str, Any]:
    plan = load_mission_plan(conn, mission_id, user_id)
    if plan is None:
        raise ValueError("mission not found")
    plan.update(patch)
    if status is not None:
        plan["status"] = status
        plan["next_step_zh"] = next_step_zh(status)
    if local_path is not None:
        plan["local_path"] = local_path
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        UPDATE entry_missions
        SET status=?, local_path=?, plan_json=?, updated_at=?
        WHERE id=? AND user_id=?
        """,
        (
            plan["status"],
            plan.get("local_path"),
            json.dumps(plan, ensure_ascii=False),
            now,
            mission_id,
            user_id,
        ),
    )
    conn.commit()
    return plan


def cited_issue_number(mission: Mission) -> int | None:
    blob = " ".join([*mission.why_now, *mission.strategy.why, *mission.strategy.steps_zh])
    match = ISSUE_NUM_RE.search(blob)
    if not match:
        return None
    return int(match.group(1))


def _load_cited_issue(full_name: str, number: int) -> dict[str, Any] | None:
    try:
        from foreshadow.github.client import GitHubClient, resolve_token
        from foreshadow.github.rest import fetch_issue
    except ImportError:
        return None
    try:
        owner, name = full_name.split("/", 1)
        client = GitHubClient(resolve_token())
        raw = fetch_issue(client, owner, name, number)
    except (OSError, ValueError, KeyError, RuntimeError):
        return None
    if not raw:
        return None
    title = str(raw.get("title") or "")[:200]
    body = str(raw.get("body") or "")[:800]
    html = str(raw.get("html_url") or "")
    return {"number": number, "title": title, "body": body, "html_url": html}


def setup_local_environment(
    conn: sqlite3.Connection,
    mission_id: int,
    user_id: int,
    data_dir: Path,
    *,
    runner: Any | None = None,
    fetch_issue: Any | None = None,
) -> dict[str, Any]:
    plan = load_mission_plan(conn, mission_id, user_id)
    if plan is None:
        raise ValueError("mission not found")
    full_name = str(plan.get("full_name") or "")
    dest = prepare_local_dir(data_dir, full_name)
    current = str(plan.get("status") or "MISSION_READY")
    if current == "MISSION_READY":
        transition(conn, mission_id, user_id, "LOCAL_SETUP")
    clone = clone_public_repo(full_name, dest, runner=runner)
    inspect = inspect_clone(Path(clone["path"]) if clone.get("path") else dest / "repo")
    mission = Mission(
        full_name=full_name,
        status="WAITING_USER_APPROVAL" if clone.get("ok") else "LOCAL_SETUP",
        strategy=recommend_entry(FeaturesBlob()),
        stage=plan.get("stage"),
        earlyness=plan.get("earlyness"),
        evidence=plan.get("evidence"),
        window=plan.get("opportunity_window"),
        access=plan.get("access"),
        why_now=list(plan.get("why_now") or []),
        needs_user_approval=True,
        local_path=str(dest),
        id=mission_id,
    )
    if isinstance(plan.get("strategy"), dict):
        from foreshadow.pipeline.strategy import StrategyResult

        raw = plan["strategy"]
        try:
            mission.strategy = StrategyResult(
                path=raw.get("path") or "ISSUE",
                summary_zh=raw.get("summary_zh") or "",
                steps_zh=list(raw.get("steps_zh") or []),
                difficulty=raw.get("difficulty") or "Medium",
                effort=raw.get("effort") or "6h",
                allows_direct_pr=bool(raw.get("allows_direct_pr")),
                why=list(raw.get("why") or []),
            )
        except (TypeError, ValueError, KeyError):
            pass
    clone_dir = Path(clone["path"]) if clone.get("path") else dest / "repo"
    branch = (
        create_local_branch(clone_dir, runner=runner)
        if clone.get("ok")
        else {"ok": False, "status": "skipped"}
    )
    tests = (
        run_local_tests(clone_dir, runner=runner)
        if clone.get("ok")
        else {"ok": False, "status": "skipped"}
    )
    write_fork_note(dest, full_name)
    issue_n = cited_issue_number(mission)
    cited = None
    if issue_n is not None:
        try:
            if fetch_issue is not None:
                cited = fetch_issue(full_name, issue_n)
            elif os.environ.get("FORESHADOW_SKIP_CLONE") != "1":
                cited = _load_cited_issue(full_name, issue_n)
        except (OSError, ValueError, TypeError, RuntimeError):
            cited = None
    draft = write_issue_draft(dest, mission, cited=cited)
    extra = {"clone": clone, "inspect": inspect, "cited_issue": cited or {}}
    write_mission_doc(dest, mission, extra=extra)
    dest_status: Status = "WAITING_USER_APPROVAL" if clone.get("ok") else "LOCAL_SETUP"
    after_setup = str(
        conn.execute(
            "SELECT status FROM entry_missions WHERE id=? AND user_id=?",
            (mission_id, user_id),
        ).fetchone()[0]
    )
    if dest_status != after_setup and dest_status in ALLOWED.get(after_setup, set()):
        transition(conn, mission_id, user_id, dest_status)
    updated = patch_mission_plan(
        conn,
        mission_id,
        user_id,
        {
            "clone": clone,
            "inspect": inspect,
            "branch": branch,
            "tests": tests,
            "draft_path": str(draft),
            "draft_excerpt": draft.read_text(encoding="utf-8")[:800],
            "cited_issue": cited or {},
            "needs_user_approval": True,
            "remote_blocked": "等待你的确认才能执行任何远程 GitHub 操作。",
        },
        status=None,
        local_path=str(dest),
    )
    record_event(
        conn,
        user_id=user_id,
        mission_id=mission_id,
        full_name=full_name,
        event="local_setup",
        detail={"clone": clone.get("status"), "inspect": inspect},
    )
    record_event(
        conn,
        user_id=user_id,
        mission_id=mission_id,
        full_name=full_name,
        event="clone_ok" if clone.get("ok") else "clone_failed",
        detail={"clone": clone},
    )
    updated["clone"] = clone
    updated["inspect"] = inspect
    updated["branch"] = branch
    updated["tests"] = tests
    updated["needs_user_approval"] = True
    return {
        "mission": updated,
        "clone": clone,
        "inspect": inspect,
        "branch": branch,
        "tests": tests,
    }


def record_user_event(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    mission_id: int,
    event: str,
) -> dict[str, Any]:
    if event not in USER_EVENTS:
        raise ValueError(f"unknown event {event}")
    plan = load_mission_plan(conn, mission_id, user_id)
    if plan is None:
        raise ValueError("mission not found")
    record_event(
        conn,
        user_id=user_id,
        mission_id=mission_id,
        full_name=str(plan.get("full_name") or ""),
        event=event,
        detail={},
    )
    status_map: dict[str, Status] = {
        "abandoned": "ABANDONED",
        "user_submitted": "WAITING_MAINTAINER",
        "pr_merged": "MERGED",
        "maintainer_replied": "WAITING_MAINTAINER",
        "pr_rejected": "BLOCKED",
        "draft_approved": "DRAFT_READY",
    }
    dest = status_map.get(event)
    current = str(plan.get("status") or "")
    if dest and dest in ALLOWED.get(current, set()):
        transition(conn, mission_id, user_id, dest)
    elif event == "abandoned":
        set_status(conn, mission_id, user_id, "ABANDONED")
    elif event == "pr_merged":
        set_status(conn, mission_id, user_id, "MERGED")
    return load_mission_plan(conn, mission_id, user_id) or plan
