"""Run the real third-party contribution golden path. Never mutates GitHub."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

REPO = "Cyrax321/CONTINUUM"
ISSUE = 582


def _gh_json(args: list[str]) -> object:
    proc = subprocess.run(
        ["gh", "api", *args], capture_output=True, text=True, check=True
    )
    return json.loads(proc.stdout)


def _gh_text(path: str) -> str:
    proc = subprocess.run(
        ["gh", "api", f"repos/{REPO}/contents/{path}", "--jq", ".content"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return ""
    import base64

    return base64.b64decode("".join(proc.stdout.split())).decode("utf-8", "replace")


def fetch_features() -> dict:
    issues_raw = _gh_json([f"repos/{REPO}/issues?state=open&per_page=50"])
    assert isinstance(issues_raw, list)
    issues = [i for i in issues_raw if isinstance(i, dict) and "pull_request" not in i]
    prs_raw = _gh_json([f"repos/{REPO}/pulls?state=open&per_page=30"])
    assert isinstance(prs_raw, list)
    return {
        "language": "Python",
        "full_name": REPO,
        "html_url": f"https://github.com/{REPO}",
        "contributing": _gh_text("CONTRIBUTING.md"),
        "readme": _gh_text("README.md")[:4000],
        "tree_names": [
            "pyproject.toml",
            "src",
            "tests",
            "README.md",
            "CONTRIBUTING.md",
            "AGENTS.md",
        ],
        "pr_accept_rate": 0.5,
        "pr_merged_sample_n": 8,
        "pr_review_rate": 0.6,
        "maint_touch": 0.6,
        "issue_sample_n": len(issues),
        "bug_n": sum(
            1
            for i in issues
            if any(
                str(lab.get("name") or "").lower() in {"bug", "crash"}
                for lab in (i.get("labels") or [])
            )
        ),
        "issues": [
            {
                "number": i["number"],
                "title": i["title"],
                "state": str(i.get("state") or "open").upper(),
                "labels": [lab["name"] for lab in (i.get("labels") or [])],
                "assignees": i.get("assignees") or [],
                "updatedAt": i.get("updated_at"),
                "url": i.get("html_url"),
            }
            for i in issues
        ],
        "prs": [
            {
                "number": p["number"],
                "title": p["title"],
                "body": p.get("body") or "",
                "url": p.get("html_url"),
            }
            for p in prs_raw
            if isinstance(p, dict)
        ],
    }


def structured_task():
    from foreshadow.contribution.task import StructuredTask

    return StructuredTask(
        repository=REPO,
        task="serve: valid-JSON non-object request must not kill stdio or close HTTP unanswered",
        evidence=[
            f"https://github.com/{REPO}/issues/{ISSUE}",
            "src/continuum/serve/server.py:282 rid = req.get('id') crashes on []/null",
            "HTTP BadParams for non-object body escapes do_POST because only JSONDecodeError is caught",
        ],
        issue_number=ISSUE,
        issue_url=f"https://github.com/{REPO}/issues/{ISSUE}",
        expected_behavior=(
            "stdio answers bad_request and keeps the loop; HTTP returns 400 JSON "
            "and leaves the server up. Object requests still dispatch."
        ),
        acceptance_criteria=[
            "echo '[]' into serve_stdio does not AttributeError / exit 1",
            "HTTP POST of [] or null returns 400 with a JSON error body",
            "existing tests/test_serve.py and tests/test_serve_http.py still pass",
            "add a regression test for the non-object body",
        ],
        constraints=[
            "minimal change in src/continuum/serve/server.py plus tests",
            "do not refactor unrelated serve code",
        ],
        relevant_files=[
            "src/continuum/serve/server.py",
            "tests/test_serve.py",
            "tests/test_serve_http.py",
        ],
        contribution_rules=[
            "CONTRIBUTING.md: clone, venv, pip install -e '.[dev]', pytest",
            "AGENTS.md: no force-push, no AI attribution, follow PR template later",
            "PRs are welcome; no CLA/DCO required",
        ],
        test_commands=[
            (
                "python -m pytest tests/test_serve.py tests/test_serve_http.py "
                "-o addopts= --tb=short -q"
            )
        ],
        forbidden_actions=[
            "git push",
            "git remote add",
            "gh pr create",
            "call GitHub with a credential",
        ],
        why=(
            "Issue #582 documents a crash on main: a JSON array or null takes "
            "down the stdio durability loop and closes HTTP unanswered. "
            "Open PR #577 is HTTP framing (#533), not this payload-shape hole."
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", default="")
    args = parser.parse_args()
    from foreshadow.contribution.executor import ContributionJob, run_contribution
    from foreshadow.contribution.jobs import persist_job
    from foreshadow.contribution.mini_swe import MiniSweExecutor
    from foreshadow.contribution.package import build_package
    from foreshadow.contribution.task import from_entry
    from foreshadow.db import connect, migrate
    from foreshadow.entry import analyze_entry
    from foreshadow.paths import resolve_data_dir

    started = time.time()
    features = fetch_features()
    strategy = analyze_entry(features, now=datetime.now(UTC), language="Python")
    rec = strategy.recommended
    print("PLAN A", rec.route, rec.issue_number, rec.title)
    for alt in strategy.alternatives:
        print("ALT", alt.route, alt.issue_number, alt.title)

    extra = {
        "expected_behavior": structured_task().expected_behavior,
        "acceptance_criteria": list(structured_task().acceptance_criteria),
        "relevant_files": list(structured_task().relevant_files),
        "test_commands": list(structured_task().test_commands),
        "constraints": list(structured_task().constraints),
        "why": structured_task().why,
        "evidence": list(structured_task().evidence),
        "issue_url": structured_task().issue_url,
    }
    from_plan = from_entry(REPO, strategy.as_dict(), extra=extra)
    task = structured_task()
    if from_plan.issue_number == ISSUE:
        task = from_plan
        if not task.test_commands:
            task.test_commands = structured_task().test_commands
        if not task.relevant_files:
            task.relevant_files = structured_task().relevant_files

    home = resolve_data_dir()
    conn = connect(home / "foreshadow.sqlite3")
    migrate(conn)
    row = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()
    uid = int(row[0]) if row else 0
    work = Path(args.work_dir) if args.work_dir else home / "poc" / "continuum-582"
    work.mkdir(parents=True, exist_ok=True)
    job = ContributionJob(
        user_id=uid,
        full_name=REPO,
        backend="mini_swe_agent",
        work_dir=work,
        task={
            "structured": task.as_dict(),
            "why": task.why,
            "entry": strategy.as_dict(),
        },
        why=task.why,
    )
    persist_job(conn, job)
    executor = MiniSweExecutor(docker=True)
    artifact = run_contribution(job, executor=executor, conn=conn)
    pkg = build_package(job, artifact, structured=task, qa_ok=artifact.qa_ok)
    elapsed = time.time() - started
    pkg["wall_time_s"] = round(elapsed, 1)
    pkg["entry"] = strategy.as_dict()
    pkg["network"] = executor.last_network_note
    out = work / "package.json"
    out.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("STATUS", job.status)
    print("QA", pkg.get("qa"), "files", pkg.get("files_changed"))
    print("WALL", elapsed)
    print("WROTE", out)
    conn.close()
    return 0 if artifact.qa_ok and artifact.tests_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
