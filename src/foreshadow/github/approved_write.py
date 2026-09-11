"""Gate-2 GitHub writes. Radar GitHubClient stays GET-only."""

from __future__ import annotations

import os
from typing import Any

from foreshadow.contribution.approval import (
    ALLOWED_REMOTE_ACTIONS,
    BLOCKED_REMOTE_ACTIONS,
)
from foreshadow.contribution.submit import RemoteWriteRefused


def write_token() -> str | None:
    raw = os.environ.get("FORESHADOW_WRITE_TOKEN") or ""
    return raw.strip() or None


class ApprovedGitHubPort:
    """GET via the radar client; writes only with FORESHADOW_WRITE_TOKEN."""

    is_fake = False

    def __init__(self, reader: Any | None = None) -> None:
        self._reader = reader
        self._token = write_token()
        self.calls: list[str] = []

    def _read(self) -> Any:
        if self._reader is not None:
            return self._reader
        from foreshadow.github.client import GitHubClient, resolve_token

        self._reader = GitHubClient(token=resolve_token())
        return self._reader

    def get_issue(self, repo: str, number: int) -> dict[str, Any]:
        self.calls.append(f"get_issue:{repo}:{number}")
        resp = self._read().get(f"/repos/{repo}/issues/{number}")
        return resp.json() if hasattr(resp, "json") else dict(resp)

    def list_open_prs(self, repo: str) -> list[dict[str, Any]]:
        self.calls.append(f"list_open_prs:{repo}")
        resp = self._read().get(f"/repos/{repo}/pulls", params={"state": "open"})
        data = resp.json() if hasattr(resp, "json") else resp
        return list(data or [])

    def get_ref(self, repo: str, ref: str) -> str:
        self.calls.append(f"get_ref:{repo}:{ref}")
        resp = self._read().get(f"/repos/{repo}/git/ref/heads/{ref}")
        body = resp.json() if hasattr(resp, "json") else resp
        sha = body.get("object", {}).get("sha") if isinstance(body, dict) else None
        return str(sha or "")

    def diff_names(self, repo: str, base: str, head: str) -> list[str]:
        self.calls.append(f"diff_names:{base}:{head}")
        resp = self._read().get(f"/repos/{repo}/compare/{base}...{head}")
        body = resp.json() if hasattr(resp, "json") else resp
        files = body.get("files") if isinstance(body, dict) else []
        return [str(f.get("filename")) for f in files or [] if f.get("filename")]

    def get_pull(self, repo: str, number: int) -> dict[str, Any]:
        self.calls.append(f"get_pull:{repo}:{number}")
        resp = self._read().get(f"/repos/{repo}/pulls/{number}")
        return resp.json() if hasattr(resp, "json") else dict(resp)

    def ensure_fork(self, repo: str) -> str:
        return self._write("fork", repo)

    def ensure_branch(self, repo: str, branch: str, sha: str) -> str:
        return self._write("push_branch", repo)

    def push_commit(self, repo: str, branch: str, sha: str) -> str:
        return self._write("push_branch", repo)

    def find_pr(self, repo: str, *, head: str, base: str) -> dict[str, Any] | None:
        self.calls.append(f"find_pr:{repo}:{head}")
        for pr in self.list_open_prs(repo):
            pr_head = ""
            raw = pr.get("head")
            if isinstance(raw, dict):
                pr_head = str(raw.get("label") or raw.get("ref") or "")
            want = str(head).split(":")[-1]
            got = str(pr_head).split(":")[-1]
            if got == want and str(pr.get("base", {}).get("ref") if isinstance(pr.get("base"), dict) else pr.get("base")) == base:
                return pr
        return None

    def create_pr(
        self,
        repo: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict[str, Any]:
        self._write("create_pr", repo)
        raise RemoteWriteRefused("create_pr requires FORESHADOW_WRITE_TOKEN")

    def _write(self, action: str, repo: str) -> str:
        self.calls.append(f"{action}:{repo}")
        if action in BLOCKED_REMOTE_ACTIONS or action not in ALLOWED_REMOTE_ACTIONS:
            raise RemoteWriteRefused(action)
        if not self._token:
            raise RemoteWriteRefused("FORESHADOW_WRITE_TOKEN missing; no remote write")
        raise RemoteWriteRefused(
            "real third-party write port is armed only for an interactive Gate-2 click"
        )


class ClientPullReader:
    def __init__(self, client: Any) -> None:
        self.client = client

    def get_pull(self, repo: str, number: int) -> dict[str, Any]:
        resp = self.client.get(f"/repos/{repo}/pulls/{number}")
        return resp.json() if hasattr(resp, "json") else dict(resp)
