"""Git evidence captured outside the coding executor's control."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from foreshadow.contribution.executor import ContributionError


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "-c", "core.hooksPath=/dev/null", *args],
        text=True,
    )


def require_clean(path: Path) -> str:
    status = git(path, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise ContributionError("PREEXISTING_WORKTREE_CONTAMINATION")
    return status


def begin(job) -> None:
    path = Path(job.sandbox_path)
    status = require_clean(path)
    job.task["implementation"] = {
        "mode": "autonomous_executor",
        "backend": job.backend,
        "clean_before": status == "",
        "upstream_head": git(path, "rev-parse", "HEAD").strip(),
        "pre_status": status,
        "pre_tree_hash": git(path, "rev-parse", "HEAD^{tree}").strip(),
        "branch": git(path, "branch", "--show-current").strip(),
        "executor_started": datetime.now(UTC).isoformat(),
    }


def finish(job) -> None:
    evidence = job.task.get("implementation", {})
    if evidence.get("mode") != "autonomous_executor":
        return
    path = Path(job.sandbox_path)
    git(path, "add", "-A")
    evidence.update(
        {
            "executor_finished": datetime.now(UTC).isoformat(),
            "post_diff": git(
                path, "diff", "--cached", "--no-ext-diff", evidence["upstream_head"]
            ),
            "diff_stat": git(
                path, "diff", "--cached", "--stat", evidence["upstream_head"]
            ),
        }
    )
