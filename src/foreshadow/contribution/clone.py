"""Public clone for contribution jobs. Never injects GitHub credentials."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from foreshadow.contribution.executor import ContributionError

_TOKEN_KEYS = (
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "GIT_ASKPASS",
    "GIT_TERMINAL_PROMPT",
)


def git_env_without_tokens() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _TOKEN_KEYS and "TOKEN" not in key and "SECRET" not in key
    }
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def clone_from_url(url: str, dest: Path, *, depth: int = 1) -> Path:
    """Clone ``url`` to ``dest`` without credentials, then drop remotes."""
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise ContributionError(f"clone destination is not empty: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", f"--depth={depth}", "--single-branch", url, str(dest)]
    try:
        subprocess.run(
            cmd,
            check=True,
            env=git_env_without_tokens(),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.CalledProcessError as exc:
        raise ContributionError(
            f"clone failed: {(exc.stderr or exc.stdout or '')[-400:]}"
        ) from exc
    _harden_clone(dest)
    return dest


def clone_public_github(full_name: str, dest: Path) -> Path:
    owner, _, repo = full_name.partition("/")
    if not owner or not repo or "/" in repo:
        raise ContributionError(f"need owner/repo, got {full_name!r}")
    url = f"https://github.com/{owner}/{repo}.git"
    return clone_from_url(url, dest)


def _harden_clone(dest: Path) -> None:
    env = git_env_without_tokens()
    subprocess.run(
        ["git", "-C", str(dest), "remote", "remove", "origin"],
        env=env,
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["git", "-C", str(dest), "config", "core.hooksPath", "/dev/null"],
        env=env,
        capture_output=True,
        check=False,
    )
