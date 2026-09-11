"""Gate-2 GitHub transport. It exposes only fork, branch push, and PR creation."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from foreshadow import __version__
from foreshadow.contribution.approval import (
    ALLOWED_REMOTE_ACTIONS,
    BLOCKED_REMOTE_ACTIONS,
)
from foreshadow.contribution.submit import RemoteWriteRefused
from foreshadow.github.client import redact

_API_VERSION = "2022-11-28"


def write_token() -> str | None:
    raw = os.environ.get("FORESHADOW_WRITE_TOKEN") or ""
    return raw.strip() or None


class ApprovedGitHubPort:
    """Use one write credential for the three Gate-2 actions only."""

    is_fake = False

    def __init__(
        self,
        reader: Any | None = None,
        *,
        token: str | None = None,
        client: httpx.Client | None = None,
        bundle_path: Path | str | None = None,
        repo_path: Path | str | None = None,
        validated_base_sha: str = "",
        source_repo: str = "",
        git_runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self._reader = reader
        self._token = token if token is not None else write_token()
        self._client = client or httpx.Client(
            base_url="https://api.github.com",
            timeout=30.0,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": _API_VERSION,
                "User-Agent": f"foreshadow-radar/{__version__}",
            },
        )
        self._bundle_path = Path(bundle_path) if bundle_path else None
        self._repo_path = Path(repo_path) if repo_path else None
        self._validated_base_sha = str(validated_base_sha)
        self._source_repo = str(source_repo)
        self._git_runner = git_runner
        self._login = ""
        self.calls: list[str] = []

    def _read(self) -> Any:
        if self._reader is None:
            from foreshadow.github.client import GitHubClient

            token = (
                self._token
                or os.environ.get("GITHUB_TOKEN")
                or os.environ.get("GH_TOKEN")
            )
            if not token:
                raise RemoteWriteRefused("GitHub read credential is missing")
            self._reader = GitHubClient(token=token)
        return self._reader

    def _api(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> httpx.Response:
        method = method.upper()
        if method not in {"GET", "POST"}:
            raise RemoteWriteRefused(f"GitHub method {method} is outside Gate 2")
        if method == "POST" and not path.endswith(("/forks", "/pulls")):
            raise RemoteWriteRefused(f"GitHub endpoint {path} is outside Gate 2")
        if not self._token:
            raise RemoteWriteRefused("FORESHADOW_WRITE_TOKEN is missing")
        try:
            response = self._client.request(
                method,
                path,
                json=json,
                params=params,
                headers={"Authorization": f"Bearer {self._token}"},
            )
        except httpx.HTTPError as exc:
            raise RemoteWriteRefused(redact(str(exc), self._token)) from exc
        if allow_not_found and response.status_code == 404:
            return response
        if response.status_code >= 400:
            detail = redact(response.text[:500], self._token)
            raise RemoteWriteRefused(
                f"GitHub {method} {path} returned {response.status_code}: {detail}"
            )
        return response

    def _identity(self) -> tuple[str, frozenset[str]]:
        response = self._api("GET", "/user")
        body = response.json()
        login = str(body.get("login") or "") if isinstance(body, dict) else ""
        if not login:
            raise RemoteWriteRefused("write credential has no GitHub identity")
        self._login = login
        scopes = frozenset(
            item.strip()
            for item in response.headers.get("x-oauth-scopes", "").split(",")
            if item.strip()
        )
        return login, scopes

    def credential_ready(self, repo: str) -> bool:
        try:
            login, scopes = self._identity()
            source = self._api("GET", f"/repos/{repo}").json()
            permissions = source.get("permissions") if isinstance(source, dict) else {}
            if isinstance(permissions, dict) and permissions.get("push") is True:
                return True
            name = repo.split("/", 1)[1]
            own = self._api("GET", f"/repos/{login}/{name}", allow_not_found=True)
            if own.status_code == 200:
                body = own.json()
                parent = body.get("parent") if isinstance(body, dict) else {}
                own_permissions = (
                    body.get("permissions") if isinstance(body, dict) else {}
                )
                return bool(
                    isinstance(parent, dict)
                    and str(parent.get("full_name") or "").lower() == repo.lower()
                    and isinstance(own_permissions, dict)
                    and own_permissions.get("push") is True
                    and ({"public_repo", "repo"} & scopes)
                )
            return bool({"public_repo", "repo"} & scopes)
        except (RemoteWriteRefused, KeyError, TypeError, ValueError):
            return False

    def transport_ready(self, sha: str) -> bool:
        if shutil.which("git") is None:
            return False
        if self._local_has_commit(sha):
            return True
        bundle = self._bundle_path
        if bundle is None or not bundle.is_file():
            return False
        result = self._git_runner(
            ["git", "bundle", "list-heads", str(bundle)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        return any(line.split()[:1] == [sha] for line in result.stdout.splitlines())

    def _local_has_commit(self, sha: str) -> bool:
        if self._repo_path is None or not self._repo_path.is_dir():
            return False
        result = self._git_runner(
            [
                "git",
                "-C",
                str(self._repo_path),
                "cat-file",
                "-e",
                f"{sha}^{{commit}}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def get_issue(self, repo: str, number: int) -> dict[str, Any]:
        self.calls.append(f"get_issue:{repo}:{number}")
        response = self._read().get(f"/repos/{repo}/issues/{number}")
        return response.json() if hasattr(response, "json") else dict(response)

    def list_open_prs(self, repo: str) -> list[dict[str, Any]]:
        self.calls.append(f"list_open_prs:{repo}")
        response = self._read().get(
            f"/repos/{repo}/pulls", params={"state": "open", "per_page": 100}
        )
        data = response.json() if hasattr(response, "json") else response
        return list(data or [])

    def get_ref(self, repo: str, ref: str) -> str:
        self.calls.append(f"get_ref:{repo}:{ref}")
        response = self._read().get(
            f"/repos/{repo}/git/ref/heads/{quote(ref, safe='')}"
        )
        body = response.json() if hasattr(response, "json") else response
        sha = body.get("object", {}).get("sha") if isinstance(body, dict) else None
        return str(sha or "")

    def diff_names(self, repo: str, base: str, head: str) -> list[str]:
        self.calls.append(f"diff_names:{base}:{head}")
        response = self._read().get(f"/repos/{repo}/compare/{base}...{head}")
        body = response.json() if hasattr(response, "json") else response
        files = body.get("files") if isinstance(body, dict) else []
        return [
            str(item.get("filename")) for item in files or [] if item.get("filename")
        ]

    def get_pull(self, repo: str, number: int) -> dict[str, Any]:
        self.calls.append(f"get_pull:{repo}:{number}")
        response = self._read().get(f"/repos/{repo}/pulls/{number}")
        return response.json() if hasattr(response, "json") else dict(response)

    def ensure_fork(self, repo: str) -> str:
        self.calls.append(f"fork:{repo}")
        login, _scopes = self._identity()
        source = self._api("GET", f"/repos/{repo}").json()
        permissions = source.get("permissions") if isinstance(source, dict) else {}
        if isinstance(permissions, dict) and permissions.get("push") is True:
            self._source_repo = repo
            return repo
        name = repo.split("/", 1)[1]
        target = f"{login}/{name}"
        own = self._api("GET", f"/repos/{target}", allow_not_found=True)
        if own.status_code == 200:
            body = own.json()
            parent = body.get("parent") if isinstance(body, dict) else {}
            if (
                not isinstance(parent, dict)
                or str(parent.get("full_name") or "").lower() != repo.lower()
            ):
                raise RemoteWriteRefused(f"{target} exists but is not a fork of {repo}")
        else:
            assert_action_allowed("fork")
            post_error: RemoteWriteRefused | None = None
            try:
                self._api(
                    "POST",
                    f"/repos/{repo}/forks",
                    json={"default_branch_only": True},
                )
            except RemoteWriteRefused as exc:
                # A timeout can happen after GitHub accepted the fork request.
                # Poll the intended fork before treating the POST as failed.
                post_error = exc
            for _ in range(20):
                own = self._api("GET", f"/repos/{target}", allow_not_found=True)
                if own.status_code == 200:
                    break
                time.sleep(0.5)
            if own.status_code != 200:
                if post_error is not None:
                    raise post_error
                raise RemoteWriteRefused(f"fork {target} was not ready before timeout")
        body = own.json()
        own_permissions = body.get("permissions") if isinstance(body, dict) else {}
        if isinstance(own_permissions, dict) and own_permissions.get("push") is False:
            raise RemoteWriteRefused(f"write credential cannot push to {target}")
        self._source_repo = repo
        return target

    def ensure_branch(self, repo: str, branch: str, sha: str) -> str:
        self.calls.append(f"push_branch:{repo}:{branch}")
        response = self._api(
            "GET",
            f"/repos/{repo}/git/ref/heads/{quote(branch, safe='')}",
            allow_not_found=True,
        )
        if response.status_code == 404:
            return sha
        body = response.json()
        current = body.get("object", {}).get("sha") if isinstance(body, dict) else None
        if str(current or "") != sha:
            raise RemoteWriteRefused(
                f"branch {repo}:{branch} exists at another commit; force-push is forbidden"
            )
        return sha

    def push_commit(self, repo: str, branch: str, sha: str) -> str:
        assert_action_allowed("push_branch")
        self.calls.append(f"push_branch:{repo}:{branch}")
        if not self.transport_ready(sha):
            raise RemoteWriteRefused(
                "approved patch bundle is unavailable or has the wrong commit"
            )
        if not self._source_repo or not self._validated_base_sha:
            raise RemoteWriteRefused("submission source or validated base is missing")
        with tempfile.TemporaryDirectory(prefix="foreshadow-submit-") as raw_dir:
            repo_dir = self._repo_path if self._local_has_commit(sha) else None
            if repo_dir is None:
                assert self._bundle_path is not None
                repo_dir = Path(raw_dir) / "repo.git"
                self._git(["git", "init", "--bare", str(repo_dir)])
                self._git(
                    [
                        "git",
                        "-C",
                        str(repo_dir),
                        "fetch",
                        "--no-tags",
                        "--depth=1",
                        f"https://github.com/{self._source_repo}.git",
                        self._validated_base_sha,
                    ]
                )
                self._git(
                    ["git", "-C", str(repo_dir), "fetch", str(self._bundle_path), sha]
                )
            parent = self._git(
                ["git", "-C", str(repo_dir), "rev-parse", f"{sha}^"]
            ).stdout.strip()
            if parent != self._validated_base_sha:
                raise RemoteWriteRefused(
                    "approved commit is not based on the approved base"
                )
            askpass = Path(raw_dir) / "askpass.sh"
            askpass.write_text(
                "#!/bin/sh\ncase \"$1\" in *Username*) printf '%s\\n' x-access-token;; *) printf '%s\\n' \"$FORESHADOW_GIT_TOKEN\";; esac\n",
                encoding="utf-8",
            )
            askpass.chmod(0o700)
            env = {
                **os.environ,
                "GIT_ASKPASS": str(askpass),
                "GIT_TERMINAL_PROMPT": "0",
                "FORESHADOW_GIT_TOKEN": str(self._token or ""),
            }
            self._git(
                [
                    "git",
                    "-C",
                    str(repo_dir),
                    "push",
                    "--porcelain",
                    f"https://github.com/{repo}.git",
                    f"{sha}:refs/heads/{branch}",
                ],
                env=env,
            )
        return sha

    def _git(self, args: list[str], **kwargs: Any) -> Any:
        result = self._git_runner(
            args, check=False, capture_output=True, text=True, **kwargs
        )
        if result.returncode != 0:
            detail = redact(str(result.stderr or result.stdout), self._token)
            raise RemoteWriteRefused(f"git transport failed: {detail.strip()}")
        return result

    def find_pr(self, repo: str, *, head: str, base: str) -> dict[str, Any] | None:
        self.calls.append(f"find_pr:{repo}:{head}")
        data = self._api(
            "GET",
            f"/repos/{repo}/pulls",
            params={"state": "open", "head": head, "base": base, "per_page": 10},
        ).json()
        return dict(data[0]) if isinstance(data, list) and data else None

    def create_pr(
        self, repo: str, *, title: str, body: str, head: str, base: str
    ) -> dict[str, Any]:
        assert_action_allowed("create_pr")
        self.calls.append(f"create_pr:{repo}")
        try:
            return dict(
                self._api(
                    "POST",
                    f"/repos/{repo}/pulls",
                    json={"title": title, "body": body, "head": head, "base": base},
                ).json()
            )
        except RemoteWriteRefused:
            # GitHub may have accepted POST even when its response was lost, or
            # may return 422 after another worker created the same PR. Reconcile
            # by the approved head/base before reporting failure.
            existing = self.find_pr(repo, head=head, base=base)
            if existing is not None:
                return existing
            raise


def assert_action_allowed(action: str) -> None:
    if action in BLOCKED_REMOTE_ACTIONS or action not in ALLOWED_REMOTE_ACTIONS:
        raise RemoteWriteRefused(action)


class ClientPullReader:
    def __init__(self, client: Any) -> None:
        self.client = client

    def get_pull(self, repo: str, number: int) -> dict[str, Any]:
        resp = self.client.get(f"/repos/{repo}/pulls/{number}")
        return resp.json() if hasattr(resp, "json") else dict(resp)
