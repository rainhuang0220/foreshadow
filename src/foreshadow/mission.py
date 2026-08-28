"""Entry Mission: local plan + optional clone. Never posts to GitHub."""

from __future__ import annotations

import json
import os
import re
import shutil
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
from foreshadow.pipeline.strategy import (
    StrategyResult,
    customize_steps,
    recommend_entry,
)

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
    "PAUSED",
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
        "paused",
        "resumed",
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
    blurb: str | None = None

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
            "blurb": self.blurb,
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
    blurb: str | None = None,
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
    strat = recommend_entry(
        feat,
        s1=s1,
        access=acc,
        language=language,
        full_name=full_name,
        blurb=blurb,
    )
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
        blurb=blurb,
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
    blurb = None
    if data and data.get("language"):
        language = str(data.get("language"))
    if data and data.get("description"):
        blurb = str(data.get("description"))
    mission = build_mission(
        full_name,
        feat=feat,
        age_days=age,
        contributors=contrib,
        stars=stars,
        pushed_age_days=pushed,
        unique_issue_authors=u_issue,
        language=language,
        blurb=blurb,
    )
    dest = prepare_local_dir(data_dir, full_name)
    mission.local_path = str(dest)
    write_mission_doc(dest, mission)
    write_issue_draft(dest, mission)
    write_pr_draft(dest, mission)
    write_fork_note(dest, full_name)
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
    "MISSION_READY": {"LOCAL_SETUP", "INVESTIGATING", "ABANDONED", "PAUSED"},
    "LOCAL_SETUP": {
        "WAITING_USER_APPROVAL",
        "DRAFT_READY",
        "ABANDONED",
        "BLOCKED",
        "PAUSED",
    },
    "WAITING_USER_APPROVAL": {
        "ABANDONED",
        "BLOCKED",
        "WAITING_MAINTAINER",
        "DRAFT_READY",
        "IMPLEMENTING",
        "PAUSED",
    },
    "DRAFT_READY": {"WAITING_USER_APPROVAL", "ABANDONED", "PAUSED"},
    "INVESTIGATING": {"MISSION_READY", "ABANDONED", "PAUSED"},
    "IMPLEMENTING": {
        "DRAFT_READY",
        "WAITING_USER_APPROVAL",
        "ABANDONED",
        "BLOCKED",
        "PAUSED",
    },
    "REPRODUCING": {"PAUSED", "ABANDONED"},
    "DISCUSSING": {"PAUSED", "ABANDONED"},
    "PAUSED": {
        "LOCAL_SETUP",
        "WAITING_USER_APPROVAL",
        "DRAFT_READY",
        "IMPLEMENTING",
        "REPRODUCING",
        "DISCUSSING",
    },
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
        "PAUSED": "已暂停",
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
        "PAUSED": "可以继续任务；暂停不会向 GitHub 发请求",
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
    if mission.access is None:
        access_s = "未知（不是 0）"
    elif mission.access == 0:
        access_s = "0（已知为 0，不是未知）"
    else:
        access_s = str(mission.access)
    after_plan = ""
    hint = str(inspect.get("install_hint") or "").strip()
    if hint:
        after_plan += (
            f"README 安装命令（你自己执行，Foreshadow 不会代跑）：`{hint}`\n"
        )
    kind = inspect.get("kind")
    if kind:
        kind_zh = {
            "python": "这是 Python 仓库。",
            "pytest": "这是 Python 仓库。",
            "node": "这是 Node 仓库。",
            "rust": "这是 Rust 仓库。",
            "go": "这是 Go 仓库。",
        }.get(str(kind).lower(), f"这是 {kind} 仓库。")
        after_plan += f"{kind_zh}\n"
    if after_plan:
        after_plan += "\n"
    text = (
        f"# 今日进入计划\n\n"
        f"项目：{mission.full_name}\n\n"
        f"文件：FORESHADOW.md（只在本机，还没发到网上）\n\n"
        f"为什么现在进入：\n{why or '- （待补充）'}\n\n"
        f"阶段：{mission.stage or '—'}\n"
        f"机会窗口：{mission.window}\n"
        f"进入通道：{access_s}\n"
        f"推荐入口：{mission.strategy.summary_zh}（{mission.strategy.path}）\n"
        f"难度：{mission.strategy.difficulty}\n"
        f"预计：{mission.strategy.effort}\n"
        f"状态：{mission.status}\n"
        f"下一步：{next_step_zh(mission.status)}\n\n"
        f"行动计划：\n{steps}\n\n"
        f"{after_plan}"
        f"本地 clone：{clone.get('status') or '尚未尝试'}\n"
        f"README：{_yn(inspect, 'has_readme')}"
        f"{(' · 标题：' + str(inspect.get('readme_title'))) if inspect.get('readme_title') else ''} · "
        f"CONTRIBUTING：{_yn(inspect, 'has_contributing')}\n"
        f"{_branch_line(extra)}"
        f"{_tests_line(extra)}"
        f"仓库顶层：{', '.join(inspect.get('top_entries') or []) or '未知'}\n"
        f"README 目录：{'；'.join(inspect.get('readme_headings') or []) or '未知'}\n"
        f"CONTRIBUTING 目录：{'；'.join(inspect.get('contributing_headings') or []) or '未知'}\n"
        f"相关文件：{', '.join(inspect.get('related_files') or inspect.get('source_files') or []) or 'UNKNOWN'}\n"
        f"测试文件：{', '.join(inspect.get('test_files') or []) or 'UNKNOWN'}\n"
        f"Issue 命令：{'; '.join(inspect.get('issue_commands') or []) or 'UNKNOWN'}\n"
    )
    why_not = "\n".join(f"- {w}" for w in mission.strategy.why) or "- 默认先沟通，不默认提 PR"
    if mission.strategy.allows_direct_pr:
        text += f"\n## 可以直接 PR\n\n{why_not}\n"
    else:
        text += f"\n## 为什么不是直接 PR\n\n{why_not}\n"
    cited = extra.get("cited_issue") or {}
    if cited.get("number"):
        text += (
            f"\n引用 Issue #{cited['number']}：{cited.get('title') or ''}\n"
            f"{(cited.get('body') or '')[:400]}\n"
        )
    extra_files = ""
    if extra.get("pr_draft"):
        extra_files += (
            "若入口是代码向的，还有 PR_DRAFT.md（同样未发送，不是真正的 Pull Request）。\n"
        )
    if extra.get("reproduction_path"):
        extra_files += "还有 REPRODUCTION.md（复现记录，只在本机，未发送）。\n"
    if extra.get("benchmark_path"):
        extra_files += "还有 BENCHMARK.md（测量记录，只在本机；Foreshadow 不会代跑基准）。\n"
    if extra.get("discussion_draft_path"):
        extra_files += "还有 DISCUSSION_DRAFT.md（讨论草稿，只在本机，未发送）。\n"
    text += (
        "\n"
        "成功标准：完成推荐入口的第一步，并等你确认后才向 GitHub 发任何内容。\n\n"
        "同目录还有 ISSUE_DRAFT.md（本地草稿，未发送）。\n"
        + extra_files
        + "本目录只做本地准备。不会自动 push / 开 Issue / 开 PR。\n"
        + "等待你的确认才能执行任何远程 GitHub 操作。\n"
    )
    path = dest / "FORESHADOW.md"
    path.write_text(text, encoding="utf-8")
    return path


def _safe_repo_dir(full_name: str) -> str:
    return full_name.replace("/", "__").replace("..", "")


def _clone_looks_complete(clone_dir: Path) -> bool:
    """True only if the worktree has a usable git HEAD. Never delete leftovers."""
    git = Path(clone_dir) / ".git"
    if git.is_file():
        try:
            return "gitdir:" in git.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
    if not git.is_dir():
        return False
    if not (git / "HEAD").is_file():
        return False
    objs = git / "objects"
    if not objs.is_dir():
        return False
    pack = objs / "pack"
    try:
        if pack.is_dir() and any(pack.iterdir()):
            return True
        for child in objs.iterdir():
            if child.is_dir() and child.name not in {"info", "pack"}:
                if any(child.iterdir()):
                    return True
    except OSError:
        return False
    return False


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
    if clone_dir.exists() and (clone_dir / ".git").exists():
        if _clone_looks_complete(clone_dir):
            return {"ok": True, "status": "exists", "path": str(clone_dir), "error": None}
        return {
            "ok": False,
            "status": "incomplete",
            "error": "本地 repo 目录不完整，Foreshadow 没有覆盖已有文件。清空该目录后才能重试 clone。",
            "path": str(clone_dir),
        }
    if clone_dir.exists():
        try:
            leftover = any(clone_dir.iterdir())
        except OSError:
            leftover = True
        if leftover:
            return {
                "ok": False,
                "status": "incomplete",
                "error": "本地 repo 目录不完整，Foreshadow 没有覆盖已有文件。清空该目录后才能重试 clone。",
                "path": str(clone_dir),
            }
    if runner is None and os.environ.get("FORESHADOW_SKIP_CLONE") == "1":
        return {
            "ok": False,
            "status": "skipped",
            "error": "clone skipped",
            "path": None,
        }
    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = clone_dir.parent / f".clone-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    run = runner or subprocess.run
    cmd = [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "clone",
        "--depth",
        "1",
        "--",
        url,
        str(staging),
    ]
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
        shutil.rmtree(staging, ignore_errors=True)
        return {
            "ok": False,
            "status": "no_git",
            "error": "本机没有 git，已跳过 clone",
            "path": None,
        }
    except subprocess.TimeoutExpired:
        shutil.rmtree(staging, ignore_errors=True)
        return {"ok": False, "status": "timeout", "error": "clone timed out", "path": None}
    code = getattr(completed, "returncode", 1)
    if code != 0:
        err = (getattr(completed, "stderr", None) or getattr(completed, "stdout", None) or "")[
            :400
        ]
        shutil.rmtree(staging, ignore_errors=True)
        return {"ok": False, "status": "failed", "error": err or "clone failed", "path": None}
    if not _clone_looks_complete(staging):
        shutil.rmtree(staging, ignore_errors=True)
        return {
            "ok": False,
            "status": "incomplete",
            "error": "clone 没有写出可用的 git HEAD，未覆盖已有目录。",
            "path": None,
        }
    try:
        os.replace(staging, clone_dir)
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        return {
            "ok": False,
            "status": "failed",
            "error": f"无法放入 repo 目录：{exc}",
            "path": None,
        }
    return {"ok": True, "status": "cloned", "path": str(clone_dir), "error": None}


def inspect_clone(clone_dir: Path | None) -> dict[str, Any]:
    empty = {
        "inspected": False,
        "has_readme": False,
        "has_contributing": False,
        "has_tests": False,
        "readme_title": None,
    }
    if clone_dir is None or not Path(clone_dir).is_dir():
        return empty
    root = Path(clone_dir)
    entries = list(root.iterdir())
    names = {p.name.lower() for p in entries}
    top = sorted(p.name for p in entries)[:20]
    readme = next(
        (p for p in entries if p.is_file() and p.name.lower().startswith("readme")),
        None,
    )
    contrib = _find_contributing(root, entries)
    headings = _doc_headings(readme) if readme else []
    contrib_headings = _doc_headings(contrib) if contrib else []
    kind = None
    if "pyproject.toml" in names or "setup.py" in names or "setup.cfg" in names:
        kind = "python"
    elif "package.json" in names:
        kind = "node"
    elif "cargo.toml" in names:
        kind = "rust"
    elif "go.mod" in names:
        kind = "go"
    return {
        "inspected": True,
        "has_readme": readme is not None,
        "has_contributing": contrib is not None,
        "has_tests": bool({"tests", "test", "spec"} & names),
        "top_entries": top,
        "readme_title": headings[0] if headings else None,
        "readme_headings": headings[:12],
        "contributing_headings": contrib_headings[:8],
        "kind": kind,
        "install_hint": _install_hint(readme) if readme else None,
        "has_source": kind is not None
        or any(
            n.endswith((".py", ".rs", ".go", ".ts", ".js", ".c", ".cpp"))
            or n in {"src", "lib", "pkg"}
            for n in names
        ),
    }


def _yn(inspect: dict[str, Any], key: str) -> str:
    if inspect.get(key):
        return "有"
    return "无" if inspect.get("inspected") else "未知"


def _branch_line(extra: dict[str, Any]) -> str:
    branch = extra.get("branch") or {}
    name = branch.get("name") or "foreshadow/entry"
    if branch.get("ok"):
        return f"本地分支：{name}（{branch.get('status') or 'ready'}，不 push）\n"
    if extra.get("clone", {}).get("ok"):
        return f"本地分支：{name}（未创建）\n"
    return "本地分支：尚未创建（clone 未完成）\n"


def _tests_line(extra: dict[str, Any]) -> str:
    tests = extra.get("tests") or {}
    kind = tests.get("kind")
    if kind == "pytest":
        return f"测试：pytest {tests.get('status') or 'collect-only'}（不装依赖）\n"
    if kind in {"node", "cargo"}:
        return f"测试：跳过（{kind}，不执行 npm/cargo）\n"
    if tests.get("status") == "skipped":
        return "测试：尚未探测或已跳过\n"
    return ""


def _find_contributing(root: Path, entries: list[Path]) -> Path | None:
    wanted = {"contributing.md", "contributing.rst", "contributing"}
    for path in entries:
        if path.is_file() and path.name.lower() in wanted:
            return path
    github = root / ".github"
    if github.is_dir():
        for name in ("CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING"):
            cand = github / name
            if cand.is_file():
                return cand
    return None


def _doc_headings(path: Path) -> list[str]:
    md = _markdown_headings(path)
    if md:
        return md
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:8000]
    except OSError:
        return []
    out: list[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        title = line.strip()
        if not title:
            continue
        if i + 1 < len(lines):
            bar = lines[i + 1].strip()
            if len(bar) >= 3 and set(bar) <= {"=", "-"}:
                out.append(title)
    return out


def _install_hint(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:8000]
    except OSError:
        return None
    for line in text.splitlines():
        raw = line.strip().lstrip("$").strip("`").strip()
        low = raw.lower()
        if "| sh" in low or "| bash" in low or "curl " in low:
            continue
        if low.startswith(
            (
                "pip install",
                "uv pip",
                "uv sync",
                "uv add",
                "poetry install",
                "npm install",
                "pnpm install",
                "yarn add",
                "cargo test",
            )
        ):
            return raw[:120]
    return None


def _markdown_headings(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:8000]
    except OSError:
        return []
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") and not s.startswith("#!"):
            title = _plain_heading(s.lstrip("#").strip())
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
_MD_MARK = re.compile(r"[*_`]+")


def _plain_heading(text: str) -> str:
    return _MD_MARK.sub("", text or "").strip()


def _keep_sidecar(path: Path) -> Path | None:
    """Do not overwrite a user's existing local draft."""
    try:
        if path.is_file() and path.stat().st_size > 0:
            return path
    except OSError:
        return None
    return None


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


_DEP_MSG = "需要用户授权安装依赖"


def detect_local_tests(clone_dir: Path) -> dict[str, Any]:
    root = Path(clone_dir)
    if not root.is_dir():
        return {"kind": "none", "reason": "no_repo"}
    names = {p.name.lower() for p in root.iterdir()}
    py = any(
        (root / n).exists()
        for n in ("pyproject.toml", "pytest.ini", "setup.py", "setup.cfg", "tox.ini")
    )
    if py:
        return {"kind": "pytest", "reason": "pytest"}
    if "package.json" in names:
        return {"kind": "node", "reason": "npm_test_blocked"}
    if "cargo.toml" in names:
        return {"kind": "cargo", "reason": "cargo_blocked"}
    return {"kind": "none", "reason": "none"}


def dependency_authorization_gate(clone_dir: Path) -> dict[str, Any] | None:
    """Record why Node/Cargo work is skipped. Never installs or builds."""
    root = Path(clone_dir)
    if not root.is_dir():
        return None
    names = {p.name.lower() for p in root.iterdir()}
    if "package.json" in names and not (root / "node_modules").is_dir():
        return {
            "status": "DEPENDENCY_REQUIRED",
            "kind": "node",
            "manifest": "package.json",
            "missing": "node_modules",
            "message_zh": _DEP_MSG,
        }
    if "cargo.toml" in names and not (root / "target").is_dir() and not (
        root / "vendor"
    ).is_dir():
        return {
            "status": "DEPENDENCY_REQUIRED",
            "kind": "cargo",
            "manifest": "Cargo.toml",
            "missing": "target",
            "message_zh": _DEP_MSG,
        }
    return None


def run_local_tests(
    clone_dir: Path,
    *,
    runner: Any | None = None,
    execute: bool = False,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """List tests on disk. Never execute pytest (clone conftest.py is untrusted)."""
    del runner, execute
    detected = detect_local_tests(clone_dir)
    if detected["kind"] != "pytest":
        return {
            "ok": False,
            "status": "skipped",
            "kind": detected["kind"],
            "reason": detected["reason"],
            "command": None,
            "returncode": None,
        }
    if os.environ.get("FORESHADOW_SKIP_TESTS") == "1":
        return {
            "ok": False,
            "status": "skipped",
            "kind": "pytest",
            "reason": "skipped",
            "command": None,
            "returncode": None,
        }
    from foreshadow.inspect_repo import list_worktree_files, test_files

    listed = test_files(list_worktree_files(Path(clone_dir)))
    requested = list(extra_args or [])
    extra = [p for p in requested if (Path(clone_dir) / p).exists()]
    if requested and not extra:
        return {
            "ok": False,
            "status": "collect_failed",
            "kind": "pytest",
            "summary": "cited test paths missing",
            "command": None,
            "returncode": None,
        }
    hits = extra or listed
    if not hits:
        return {
            "ok": False,
            "status": "skipped",
            "kind": "pytest",
            "reason": "no_test_files",
            "command": None,
            "returncode": None,
        }
    shown = hits[:8]
    return {
        "ok": True,
        "status": "collect_ok",
        "kind": "pytest",
        "summary": "listed on disk, pytest not executed: " + ", ".join(shown),
        "command": "path-check " + " ".join(shown),
        "returncode": None,
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
        "clone 完成以后，代码在 `repo/`，分支 `foreshadow/entry`。\n"
        "本文件在开始进入之前就会写好。没有 clone 时不要假设 repo/ 已经存在。\n"
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
    kept = _keep_sidecar(path)
    if kept is not None:
        return kept
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


CODE_SHAPED_PATHS = frozenset(
    {
        "BUG_FIX",
        "TEST",
        "TOOLING",
        "DOCUMENTATION",
        "FEATURE",
        "INTEGRATION",
        "PERFORMANCE",
    }
)


def write_pr_draft(dest: Path, mission: Mission) -> Path | None:
    """Local patch proposal. Never create_pr. None if path is not code-shaped."""
    if mission.strategy.path not in CODE_SHAPED_PATHS:
        return None
    path = Path(dest) / "PR_DRAFT.md"
    kept = _keep_sidecar(path)
    if kept is not None:
        return kept
    path.write_text(
        f"# 本地补丁草案（未发送）\n\n"
        f"项目：{mission.full_name}\n"
        f"入口：{mission.strategy.summary_zh}（{mission.strategy.path}）\n"
        f"标题：{_draft_title(mission)}\n\n"
        "## 这不是 GitHub Pull Request\n\n"
        "- 本文件只留在本机。\n"
        "- Foreshadow 不会 `git push`。\n"
        "- Foreshadow 不会 `create_pr`。\n"
        "- 等待你的确认才能发到 GitHub。\n\n"
        "## 建议的本地工作\n\n"
        + "\n".join(f"{i}. {s}" for i, s in enumerate(mission.strategy.steps_zh, 1))
        + "\n\n"
        "先把改动留在 `repo/` 的 `foreshadow/entry` 分支。远程发送另说。\n",
        encoding="utf-8",
    )
    return path


_LOCAL_ONLY = "等待你的确认才能发到 GitHub。\n这只是本地文件。\n"


def _reproduction_issue_block(
    cited: dict[str, Any] | None, mission: Mission
) -> str:
    cited = cited or {}
    number = cited.get("number")
    title = str(cited.get("title") or "")
    body = str(cited.get("body") or "")
    if number is None:
        number = cited_issue_number(mission)
        if number is not None and not title:
            for line in [*mission.why_now, *mission.strategy.why]:
                if "建议先看：" in line:
                    title = line.split("建议先看：", 1)[1].strip()
                    break
    if number is None:
        return "UNKNOWN"
    lines = [f"#{int(number)} {title}".rstrip()]
    if body:
        lines.append(body[:800])
    return "\n".join(lines)


def write_reproduction_doc(
    dest: Path,
    mission: Mission,
    cited: dict[str, Any] | None = None,
) -> Path | None:
    """Local reproduction notes. Never posts. None if path is not REPRODUCTION."""
    if mission.strategy.path != "REPRODUCTION":
        return None
    path = Path(dest) / "REPRODUCTION.md"
    kept = _keep_sidecar(path)
    if kept is not None:
        return kept
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(mission.strategy.steps_zh, 1))
    path.write_text(
        f"# 复现记录（本地）\n\n"
        f"项目：{mission.full_name}\n"
        f"入口：{mission.strategy.summary_zh}（REPRODUCTION）\n\n"
        f"## 针对的 Issue\n\n"
        f"{_reproduction_issue_block(cited, mission)}\n\n"
        f"## 本机怎么做\n\n"
        f"{steps}\n\n"
        "先把复现说明给维护者看，不要先改代码发到网上。\n"
        "Foreshadow 不会自动 post Issue / Discussion / PR。\n"
        f"{_LOCAL_ONLY}",
        encoding="utf-8",
    )
    return path


def write_benchmark_doc(
    dest: Path,
    mission: Mission,
    inspect: dict[str, Any] | None = None,
) -> Path | None:
    """Local measurement notes. Never runs benches. None if path is not BENCHMARK."""
    if mission.strategy.path != "BENCHMARK":
        return None
    path = Path(dest) / "BENCHMARK.md"
    kept = _keep_sidecar(path)
    if kept is not None:
        return kept
    inspect = inspect or {}
    hint = str(inspect.get("install_hint") or "").strip()
    heads = [
        str(h).strip()
        for h in (inspect.get("readme_headings") or [])
        if str(h).strip()
    ]
    hint_line = (
        f"README 安装命令（你自己执行，Foreshadow 不会代跑）：`{hint}`"
        if hint
        else "README 安装命令：UNKNOWN"
    )
    heads_line = (
        "README 目录：" + "；".join(heads) if heads else "README 目录：UNKNOWN"
    )
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(mission.strategy.steps_zh, 1))
    path.write_text(
        f"# 测量记录（本地）\n\n"
        f"项目：{mission.full_name}\n"
        f"入口：{mission.strategy.summary_zh}（BENCHMARK）\n\n"
        f"{hint_line}\n"
        f"{heads_line}\n\n"
        "Foreshadow 不会代跑基准，也不会执行 benchmark 命令。\n"
        "记下可重复的一组数字，先讨论，不要发优化补丁。\n\n"
        f"## 建议怎么做\n\n{steps}\n\n"
        f"{_LOCAL_ONLY}",
        encoding="utf-8",
    )
    return path


def write_discussion_draft(dest: Path, mission: Mission) -> Path | None:
    """Local discussion notes. Never posts. None if path is not DISCUSSION."""
    if mission.strategy.path != "DISCUSSION":
        return None
    path = Path(dest) / "DISCUSSION_DRAFT.md"
    kept = _keep_sidecar(path)
    if kept is not None:
        return kept
    why = "\n".join(f"- {w}" for w in mission.why_now) or "- （待补充）"
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(mission.strategy.steps_zh, 1))
    path.write_text(
        f"# 讨论草稿（本地）\n\n"
        f"项目：{mission.full_name}\n"
        f"入口：{mission.strategy.summary_zh}（DISCUSSION）\n"
        f"标题：{_draft_title(mission)}\n\n"
        f"## 为什么先讨论\n{why}\n\n"
        f"## 建议怎么说\n{steps}\n\n"
        "先观察维护者会不会回应，不要改代码。\n"
        "Foreshadow 不会自动 post Issue / Discussion / PR。\n"
        f"{_LOCAL_ONLY}",
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
        blurb=plan.get("blurb"),
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


_PYTEST_HEAD = re.compile(
    r"^\s*(?:pytest|python3?\s+-m\s+pytest)\b",
    re.IGNORECASE,
)
_PIPELINE_LABELS = {
    "clone": "克隆仓库",
    "branch": "创建本地分支",
    "inspect": "检查仓库",
    "issue": "读取 Issue",
    "tests": "收集测试",
    "drafts": "生成草稿",
    "waiting_approval": "等待确认",
}
_HITL_NEXT = "等待你的确认才能执行任何远程 GitHub 操作。"


def _pipeline_step(step_id: str, status: str, evidence: Any) -> dict[str, Any]:
    return {
        "id": step_id,
        "label_zh": _PIPELINE_LABELS.get(step_id, step_id),
        "status": status,
        "evidence": evidence,
    }


_CLONE_EVIDENCE = {
    "cloned": "已克隆到本机",
    "exists": "本地已有仓库",
    "failed": "克隆失败，任务仍保留",
    "no_git": "本机没有 git",
    "skipped": "已跳过克隆",
    "timeout": "克隆超时",
    "invalid": "仓库名无效",
    "incomplete": "本地目录不完整，未覆盖",
}


def _clone_pipeline_status(clone: dict[str, Any]) -> str:
    if clone.get("ok"):
        return "done"
    if str(clone.get("status") or "") in {"skipped", "no_git"}:
        return "skipped"
    return "failed"


def _clone_evidence(clone: dict[str, Any]) -> str:
    st = str(clone.get("status") or "")
    if st in _CLONE_EVIDENCE:
        return _CLONE_EVIDENCE[st]
    err = str(clone.get("error") or "").strip()
    return err[:120] or st or "未知"


def _inspect_evidence(inspect: dict[str, Any]) -> str:
    title = _plain_heading(str(inspect.get("readme_title") or ""))
    if title:
        return title
    if inspect.get("inspected"):
        return "已检查仓库"
    return "未检查"


def _issue_evidence(cited: dict[str, Any]) -> str:
    number = cited.get("number")
    if number:
        return f"#{number}"
    return "无 Issue 引用"


def _tests_evidence(tests: dict[str, Any]) -> str:
    if tests.get("message_zh"):
        return str(tests["message_zh"])
    st = str(tests.get("status") or "")
    if st == "DEPENDENCY_REQUIRED":
        return "需要用户授权安装依赖"
    if st in {"collect_ok", "passed"}:
        return "已收集测试"
    if st in {"collect_failed", "failed", "timeout"}:
        return "测试收集失败"
    if st in {"skipped", ""} or tests.get("kind") in {None, "none"}:
        return "跳过（无允许的测试命令）"
    return st


def _task_log_has(dest: Path, task: str) -> bool:
    path = Path(dest) / "TASK_LOG.md"
    try:
        if not path.is_file():
            return False
        return f"TASK: {task}\n" in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _branch_pipeline_status(branch: dict[str, Any], *, cloned: bool) -> str:
    if branch.get("ok"):
        return "done"
    if not cloned or str(branch.get("status") or "") == "skipped":
        return "skipped"
    return "failed"


def _tests_pipeline_status(tests: dict[str, Any]) -> str:
    st = str(tests.get("status") or "")
    if st == "DEPENDENCY_REQUIRED" or tests.get("gate") == "DEPENDENCY_REQUIRED":
        return "DEPENDENCY_REQUIRED"
    if tests.get("ok") or st in {"collect_ok", "passed"}:
        return "done"
    if st in {"collect_failed", "failed", "timeout"}:
        return "failed"
    return "skipped"


def _build_setup_pipeline(
    *,
    clone: dict[str, Any],
    branch: dict[str, Any],
    inspect: dict[str, Any],
    cited: dict[str, Any] | None,
    tests: dict[str, Any],
    drafts_ok: bool,
    waiting: bool,
) -> list[dict[str, Any]]:
    cited = cited or {}
    issue_n = cited.get("number")
    return [
        _pipeline_step(
            "clone",
            _clone_pipeline_status(clone),
            _clone_evidence(clone),
        ),
        _pipeline_step(
            "branch",
            _branch_pipeline_status(branch, cloned=bool(clone.get("ok"))),
            branch.get("name") or branch.get("status") or "skipped",
        ),
        _pipeline_step(
            "inspect",
            "done" if inspect.get("inspected") else "skipped",
            _inspect_evidence(inspect),
        ),
        _pipeline_step(
            "issue",
            "done" if issue_n else "skipped",
            _issue_evidence({"number": issue_n} if issue_n else cited),
        ),
        _pipeline_step(
            "tests",
            _tests_pipeline_status(tests),
            _tests_evidence(tests),
        ),
        _pipeline_step(
            "drafts",
            "done" if drafts_ok else "failed",
            "ISSUE_DRAFT.md" if drafts_ok else "missing",
        ),
        _pipeline_step(
            "waiting_approval",
            "pending" if waiting else "skipped",
            _HITL_NEXT if waiting else "clone unfinished",
        ),
    ]


def _pipeline_command(step_id: str) -> str:
    return {
        "clone": "git clone --depth 1",
        "branch": "git checkout -b foreshadow/entry",
        "inspect": "inspect worktree",
        "issue": "GET issue (read-only)",
        "tests": "path-check test files (pytest not executed)",
        "drafts": "write FORESHADOW.md ISSUE_DRAFT.md",
        "waiting_approval": "",
    }.get(step_id, "")


def _log_setup_pipeline(
    dest: Path,
    pipeline: list[dict[str, Any]],
    *,
    skip_ids: set[str] | None = None,
) -> None:
    from foreshadow.tasks import append_task_log

    skip = skip_ids or set()
    for step in pipeline:
        step_id = str(step.get("id") or "")
        if not step_id or step_id in skip:
            continue
        append_task_log(
            dest,
            task=step_id,
            command=_pipeline_command(step_id),
            result=str(step.get("evidence") or step.get("status") or ""),
            verdict="UNKNOWN",
            next_step=_HITL_NEXT if step_id == "waiting_approval" else "继续本地流水线",
        )


def _tests_from_task(collect: Any, detected: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(getattr(collect, "ok", False)),
        "status": str(getattr(collect, "status", None) or "skipped"),
        "kind": detected.get("kind"),
        "summary": (getattr(collect, "stdout", None) or "")[:400] or None,
        "error": (getattr(collect, "stderr", None) or "")[:400] or None,
        "returncode": getattr(collect, "exit_code", None),
        "artifact": getattr(collect, "artifact", None),
    }


def _pytest_collect_args(command: str, clone_dir: Path) -> list[str] | None:
    line = (command or "").strip().lstrip("$").strip("`").strip()
    if not line or not _PYTEST_HEAD.match(line):
        return None
    low = line.lower()
    if any(
        tok in low
        for tok in (
            "pip install",
            "npm install",
            "yarn ",
            "pnpm ",
            "curl ",
            "| sh",
            "| bash",
        )
    ):
        return None
    rest = _PYTEST_HEAD.sub("", line).strip()
    if not rest:
        return []
    root = Path(clone_dir).resolve()
    args: list[str] = []
    for part in rest.split():
        if part.startswith("-"):
            continue
        cand = (root / part).resolve()
        try:
            cand.relative_to(root)
        except ValueError:
            continue
        if cand.exists():
            args.append(part)
    return args


def _issue_pytest_verdict(result: dict[str, Any] | None) -> str:
    if not result:
        return "UNKNOWN"
    status = str(result.get("status") or "")
    if result.get("ok") or status == "collect_ok":
        return "FOUND_TEST_TARGET"
    if status in {"collect_failed", "failed", "timeout", "no_runner"}:
        return "TEST_COLLECTION_FAILED"
    return "UNKNOWN"


def _maybe_collect_issue_pytest(
    clone_dir: Path,
    inspect: dict[str, Any],
    *,
    runner: Any | None,
) -> dict[str, Any] | None:
    if detect_local_tests(clone_dir).get("kind") != "pytest":
        return None
    extra: list[str] = []
    for cmd in inspect.get("issue_commands") or []:
        args = _pytest_collect_args(str(cmd), clone_dir)
        if args:
            extra.extend(path for path in args if path not in extra)
    if not extra:
        return None
    return run_local_tests(clone_dir, runner=runner, execute=False, extra_args=extra)


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
    if current in {"PAUSED", "ABANDONED", "MERGED"}:
        clone = plan.get("clone") if isinstance(plan.get("clone"), dict) else {}
        return {
            "mission": {
                **plan,
                "id": mission_id,
                "status": current,
                "status_zh": status_zh(current),
            },
            "clone": clone or {"ok": False, "status": "skipped"},
            "inspect": plan.get("inspect") or {},
            "branch": plan.get("branch") or {},
            "tests": plan.get("tests") or {},
            "pipeline": plan.get("pipeline") or [],
        }
    if current == "MISSION_READY":
        transition(conn, mission_id, user_id, "LOCAL_SETUP")
    clone = clone_public_repo(full_name, dest, runner=runner)
    inspect = (
        inspect_clone(Path(clone["path"]))
        if clone.get("ok") and clone.get("path")
        else inspect_clone(None)
    )
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
        blurb=plan.get("blurb"),
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
    detected = (
        detect_local_tests(clone_dir)
        if clone.get("ok")
        else {"kind": "none", "reason": "no_clone"}
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
    if issue_n is not None and not cited:
        title = ""
        for line in [*mission.why_now, *mission.strategy.why]:
            if "建议先看：" in line:
                title = line.split("建议先看：", 1)[1].strip()
                break
        cited = {"number": issue_n, "title": title}
    from foreshadow.inspect_repo import enrich_inspect

    inspect = enrich_inspect(
        Path(clone["path"]) if clone.get("path") else dest / "repo",
        inspect,
        cited,
    )
    inspect_steps = dict(inspect)
    inspect_steps["tests"] = detected
    mission.strategy.steps_zh = customize_steps(
        mission.strategy.path,
        language=mission.strategy.language,
        full_name=full_name,
        inspect=inspect_steps,
        cited=cited,
        cloned=bool(clone.get("ok")),
        blurb=str(plan.get("blurb") or "") or None,
    )
    draft = write_issue_draft(dest, mission, cited=cited)
    pr_draft = write_pr_draft(dest, mission)
    repro = write_reproduction_doc(dest, mission, cited=cited)
    bench = write_benchmark_doc(dest, mission, inspect=inspect)
    discuss = write_discussion_draft(dest, mission)
    from foreshadow.tasks import append_task_log, run_task

    logged_tests = False
    if clone.get("ok"):
        collect = run_task(clone_dir, "collect_tests", runner=runner)
        tests = _tests_from_task(collect, detected)
        logged_tests = True
        issue_collect = _maybe_collect_issue_pytest(clone_dir, inspect, runner=runner)
        if issue_collect is not None:
            tests["issue_collect"] = {
                "ok": issue_collect.get("ok"),
                "status": issue_collect.get("status"),
                "summary": issue_collect.get("summary"),
                "command": issue_collect.get("command"),
            }
            append_task_log(
                dest,
                task="collect_tests",
                command=str(issue_collect.get("command") or ""),
                exit_code=issue_collect.get("returncode"),
                result=str(
                    issue_collect.get("summary") or issue_collect.get("status") or ""
                ),
                verdict=_issue_pytest_verdict(issue_collect),
                next_step=_HITL_NEXT,
            )
        if detected.get("kind") in {"node", "cargo"}:
            gate = dependency_authorization_gate(clone_dir)
            if gate:
                tests["ok"] = False
                tests["status"] = "DEPENDENCY_REQUIRED"
                tests["gate"] = "DEPENDENCY_REQUIRED"
                tests["kind"] = gate.get("kind") or detected.get("kind")
                tests["message_zh"] = gate["message_zh"]
    else:
        tests = {
            "ok": False,
            "status": "skipped",
            "kind": detected.get("kind") or "none",
        }
    dest_status: Status = (
        "WAITING_USER_APPROVAL"
        if clone.get("ok") and branch.get("ok")
        else "LOCAL_SETUP"
    )
    pipeline = _build_setup_pipeline(
        clone=clone,
        branch=branch,
        inspect=inspect,
        cited=cited,
        tests=tests,
        drafts_ok=(dest / "ISSUE_DRAFT.md").is_file(),
        waiting=dest_status == "WAITING_USER_APPROVAL",
    )
    if _task_log_has(dest, "clone"):
        from foreshadow.tasks import append_task_log

        append_task_log(
            dest,
            task="setup_retry",
            command="",
            result="reused existing local worktree",
            verdict="UNKNOWN",
            next_step=_HITL_NEXT,
        )
    else:
        _log_setup_pipeline(
            dest, pipeline, skip_ids={"tests"} if logged_tests else None
        )
    extra = {
        "clone": clone,
        "inspect": inspect,
        "cited_issue": cited or {},
        "pr_draft": str(pr_draft) if pr_draft else None,
        "reproduction_path": str(repro) if repro else None,
        "benchmark_path": str(bench) if bench else None,
        "discussion_draft_path": str(discuss) if discuss else None,
        "branch": branch,
        "tests": tests,
        "pipeline": pipeline,
    }
    write_mission_doc(dest, mission, extra=extra)
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
            "pipeline": pipeline,
            "draft_path": str(draft),
            "draft_excerpt": draft.read_text(encoding="utf-8")[:800],
            "pr_draft_path": str(pr_draft) if pr_draft else None,
            "reproduction_path": str(repro) if repro else None,
            "benchmark_path": str(bench) if bench else None,
            "discussion_draft_path": str(discuss) if discuss else None,
            "cited_issue": cited or {},
            "strategy": mission.strategy.as_dict(),
            "steps_zh": list(mission.strategy.steps_zh),
            "blurb": mission.blurb,
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
    updated["pipeline"] = pipeline
    updated["needs_user_approval"] = True
    return {
        "mission": updated,
        "clone": clone,
        "inspect": inspect,
        "branch": branch,
        "tests": tests,
        "pipeline": pipeline,
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
        "paused": "PAUSED",
    }
    dest = status_map.get(event)
    current = str(plan.get("status") or "")
    if event == "resumed" and current == "PAUSED":
        clone = plan.get("clone") if isinstance(plan.get("clone"), dict) else {}
        dest = "WAITING_USER_APPROVAL" if clone.get("ok") else "LOCAL_SETUP"
    if dest == "SUBMITTED":
        dest = None
    if dest and dest in ALLOWED.get(current, set()):
        transition(conn, mission_id, user_id, dest)
    elif event == "abandoned":
        set_status(conn, mission_id, user_id, "ABANDONED")
    elif event == "pr_merged":
        set_status(conn, mission_id, user_id, "MERGED")
    return load_mission_plan(conn, mission_id, user_id) or plan
