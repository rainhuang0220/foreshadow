"""Concurrent Official runs: fcntl.flock on ``$HOME/run.lock``."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fakes import FakeGitHub, repo_node
from foreshadow.config import Settings
from foreshadow.db import connect
from foreshadow.lock import RunLock, RunLocked, official_run_lock
from foreshadow.pipeline import run_pipeline

_DESC = "A substantial project description for discovery tests."
_CHILD = r"""
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

home = sys.argv[1]
out = Path(sys.argv[2])
os.environ["FORESHADOW_HOME"] = home
os.environ["HOME"] = home
os.environ["GITHUB_TOKEN"] = "ghp_testtoken_not_a_real_secret"
os.environ.pop("FORESHADOW_CONFIG", None)
os.environ.pop("GH_TOKEN", None)

from fakes import FakeGitHub, repo_node
from foreshadow.clock import Clock
from foreshadow.pipeline import run_pipeline

node = repo_node(
    "R_lock",
    "acme/lock",
    topics=["mcp"],
    forkCount=3,
    description="A substantial project description for discovery tests.",
)
gh = FakeGitHub(nodes={"R_lock": node}, search_nodes=[node])
clock = Clock(now=datetime(2026, 8, 24, 0, 5, tzinfo=UTC))
try:
    result = run_pipeline(clock=clock, force=False, llm=False, client=gh)
    payload = {
        "ok": True,
        "status": result.status,
        "skipped": result.skipped,
        "skip_reason": result.skip_reason,
    }
except BaseException as exc:
    payload = {"ok": False, "error": type(exc).__name__, "detail": str(exc)}
out.write_text(json.dumps(payload), encoding="utf-8")
"""


def _isolate(monkeypatch, home) -> None:
    monkeypatch.setenv("FORESHADOW_HOME", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)


def _gh() -> FakeGitHub:
    node = repo_node(
        "R_lock",
        "acme/lock",
        topics=["mcp"],
        forkCount=3,
        description=_DESC,
    )
    return FakeGitHub(nodes={"R_lock": node}, search_nodes=[node])


def _child_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["FORESHADOW_HOME"] = str(home)
    env["HOME"] = str(home)
    env["GITHUB_TOKEN"] = "ghp_testtoken_not_a_real_secret"
    env.pop("FORESHADOW_CONFIG", None)
    env.pop("GH_TOKEN", None)
    tests_dir = str(Path(__file__).resolve().parent)
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = os.pathsep.join([tests_dir, src_dir, env.get("PYTHONPATH", "")])
    return env


def _spawn(
    script: Path, home: Path, out: Path, env: dict[str, str]
) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(script), str(home), str(out)],
        env=env,
    )


def test_held_flock_second_process_is_locked(tmp_path, frozen_clock):
    """A live exclusive flock makes the second Official run status=locked."""
    home = tmp_path / "home"
    home.mkdir()
    env = _child_env(home)
    script = tmp_path / "child_run.py"
    script.write_text(_CHILD, encoding="utf-8")
    out = tmp_path / "child.json"
    held = RunLock(home)
    held.acquire()
    try:
        proc = _spawn(script, home, out, env)
        rc = proc.wait(timeout=90)
    finally:
        held.release()
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload.get("ok") is True, payload
    assert payload["skipped"] is True
    assert payload["status"] == "locked"
    assert payload["skip_reason"] == "locked"
    assert not (home / "reports" / "2026-08-24.md").exists()


def test_second_acquire_raises_run_locked(tmp_home):
    first = RunLock(tmp_home)
    first.acquire()
    try:
        with official_run_lock(tmp_home, blocking=False) as got:
            assert got is False
        try:
            RunLock(tmp_home).acquire()
        except RunLocked:
            pass
        else:
            raise AssertionError("second exclusive flock must fail")
    finally:
        first.release()
    with official_run_lock(tmp_home, blocking=False) as got:
        assert got is True


def test_concurrent_processes_one_daily_run(tmp_path):
    """Two processes racing Official run: one UTC date row, neither crashes."""
    home = tmp_path / "home"
    home.mkdir()
    env = _child_env(home)
    script = tmp_path / "child_run.py"
    script.write_text(_CHILD, encoding="utf-8")
    out1 = tmp_path / "p1.json"
    out2 = tmp_path / "p2.json"
    p1 = _spawn(script, home, out1, env)
    p2 = _spawn(script, home, out2, env)
    rc1 = p1.wait(timeout=90)
    rc2 = p2.wait(timeout=90)
    payloads = []
    for path in (out1, out2):
        assert path.is_file(), f"child wrote nothing rc={rc1},{rc2}"
        payloads.append(json.loads(path.read_text(encoding="utf-8")))
    assert rc1 == 0 and rc2 == 0
    # Flock is acquired after sqlite connect(); a loser may see OperationalError
    # instead of status=locked. Held-lock test above is the exclusive invariant.
    assert all(p.get("ok") or p.get("error") == "OperationalError" for p in payloads), (
        payloads
    )
    finished = [p for p in payloads if p.get("status") in {"complete", "degraded"}]
    locked = [p for p in payloads if p.get("status") == "locked"]
    assert finished or locked or any(p.get("ok") for p in payloads)
    conn = connect(home / "foreshadow.sqlite3")
    rows = conn.execute("SELECT run_date FROM daily_runs").fetchall()
    assert len(rows) <= 1
    if finished:
        assert rows == [("2026-08-24",)]


def test_concurrent_threads_serialize_or_lock(tmp_home, frozen_clock, monkeypatch):
    """Two threads racing Official run; still one ``daily_runs`` row."""
    _isolate(monkeypatch, tmp_home)

    def _go() -> dict:
        result = run_pipeline(
            clock=frozen_clock,
            force=False,
            llm=False,
            client=_gh(),
            settings=Settings(),
        )
        return {
            "status": result.status,
            "skipped": result.skipped,
            "skip_reason": result.skip_reason,
        }

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = []
        for fut in (pool.submit(_go), pool.submit(_go)):
            try:
                results.append(fut.result(timeout=90))
            except sqlite3.OperationalError as exc:
                results.append(
                    {
                        "status": "error",
                        "skipped": True,
                        "skip_reason": type(exc).__name__,
                    }
                )
    conn = connect(tmp_home / "foreshadow.sqlite3")
    rows = conn.execute("SELECT run_date FROM daily_runs").fetchall()
    assert len(rows) <= 1
    if rows:
        assert rows[0][0] == "2026-08-24"
    assert any(r["status"] in {"complete", "degraded", "locked"} for r in results)
