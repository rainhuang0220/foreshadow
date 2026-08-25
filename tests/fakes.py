from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from foreshadow.config import GitHubSettings
from foreshadow.github.client import GitHubError, operation_name

NOW = datetime(2026, 8, 24, 0, 5, tzinfo=UTC)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        json_body: Any = None,
        *,
        headers: dict[str, str] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_body
        if json_body is not None:
            self.content = json.dumps(json_body).encode()
            self.text = self.content.decode()
        else:
            self.content = text.encode()
            self.text = text

    def json(self) -> Any:
        return self._json


def repo_node(node_id: str, full_name: str, **over: Any) -> dict[str, Any]:
    """GraphQL Repository node with required Phase A fields. No watchers."""
    topics = over.pop("topics", None)
    topic_nodes = [{"topic": {"name": t}} for t in (topics or [])]
    node: dict[str, Any] = {
        "id": node_id,
        "databaseId": over.pop("databaseId", None),
        "nameWithOwner": full_name,
        "url": f"https://github.com/{full_name}",
        "description": f"repo {full_name}",
        "createdAt": "2026-05-01T00:00:00Z",
        "pushedAt": "2026-08-20T00:00:00Z",
        "updatedAt": "2026-08-20T00:00:00Z",
        "isFork": False,
        "isArchived": False,
        "isDisabled": False,
        "isEmpty": False,
        "isTemplate": False,
        "isMirror": False,
        "hasIssuesEnabled": True,
        "stargazerCount": 100,
        "forkCount": 10,
        "primaryLanguage": {"name": "Python"},
        "licenseInfo": {"spdxId": "MIT", "key": "mit"},
        "repositoryTopics": {"nodes": topic_nodes},
        "defaultBranchRef": {
            "name": "main",
            "target": {"oid": "abc123", "committedDate": "2026-08-20T00:00:00Z"},
        },
        "issuesOpen": {"totalCount": 4},
        "issuesClosed": {"totalCount": 1},
        "prsOpen": {"totalCount": 1},
        "discussions": {"totalCount": 0},
        "contributing": None,
        "readme": {"text": "# Hi\npip install x\n", "byteSize": 20},
        "issuesOpenSample": {"totalCount": 4, "nodes": []},
        "issuesClosedSample": {"nodes": []},
        "gfi": {"totalCount": 0},
        "gfiHyphen": {"totalCount": 0},
        "helpWanted": {"totalCount": 0},
        "helpWantedHyphen": {"totalCount": 0},
    }
    node.update(over)
    if node["databaseId"] is None:
        node["databaseId"] = int(hashlib.sha256(node_id.encode()).hexdigest()[:15], 16)
    return node


def seed_repo(
    conn: Any,
    node_id: str,
    full_name: str,
    *,
    now: str = "2026-08-24T00:05:00+00:00",
    status: str = "active",
    **fields: Any,
) -> int:
    base = full_name.split("#", 1)[0]
    if "/" in base:
        owner, name = base.split("/", 1)
    else:
        owner, name = "", base
    conn.execute(
        """
        INSERT INTO repos(
          node_id, database_id, full_name, owner, name, html_url, description,
          language, license_spdx, created_at, default_branch, has_issues,
          is_fork, is_archived, is_disabled, is_empty, is_template, is_mirror,
          status, first_seen_at, last_seen_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            node_id,
            fields.get("database_id"),
            full_name,
            fields.get("owner", owner),
            fields.get("name", name.split("#", 1)[0]),
            fields.get("html_url", f"https://github.com/{full_name.split('#', 1)[0]}"),
            fields.get("description"),
            fields.get("language"),
            fields.get("license_spdx"),
            fields.get("created_at", "2026-05-01T00:00:00Z"),
            fields.get("default_branch", "main"),
            fields.get("has_issues", 1),
            int(fields.get("is_fork", 0)),
            int(fields.get("is_archived", 0)),
            int(fields.get("is_disabled", 0)),
            int(fields.get("is_empty", 0)),
            int(fields.get("is_template", 0)),
            int(fields.get("is_mirror", 0)),
            status,
            now,
            now,
        ),
    )
    return int(
        conn.execute("SELECT id FROM repos WHERE node_id=?", (node_id,)).fetchone()[0]
    )


def seed_review(
    conn: Any,
    repo_id: int,
    action: str,
    created_at: str,
    *,
    run_id: int | None = None,
    note: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO reviews(repo_id, action, note, run_id, created_at) VALUES (?,?,?,?,?)",
        (repo_id, action, note, run_id, created_at),
    )


def review_time(seconds_ago: int) -> str:
    return (NOW - timedelta(seconds=seconds_ago)).isoformat()


@dataclass
class FakeGitHub:
    """In-memory GitHub stand-in. ``hydrate_calls`` increments on every hydrate."""

    hydrate_calls: int = 0
    hydrate_a_calls: int = 0
    hydrate_b_calls: int = 0
    hydrate_ids: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    graphql_network_calls: int = 0
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing: set[str] = field(default_factory=set)
    b_missing: set[str] = field(default_factory=set)
    fail_ids: set[str] = field(default_factory=set)
    rest_status: dict[tuple[str, str], int] = field(default_factory=dict)
    search_nodes: list[dict[str, Any]] = field(default_factory=list)
    search_pages: list[list[dict[str, Any]]] | None = None
    search_total_override: int | None = None
    contributors: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    contributor_pages: dict[str, list[list[dict[str, Any]]]] = field(
        default_factory=dict
    )
    contributor_requests: list[tuple[str, int]] = field(default_factory=list)
    commits: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    contents: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    pulls: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    workflows: dict[str, dict[str, Any]] = field(default_factory=dict)
    community: dict[str, dict[str, Any]] = field(default_factory=dict)
    source_failures: list[Any] = field(default_factory=list)
    graphql_used: int = 0
    rest_used: int = 0
    graphql_remaining: int | None = 5000
    budget_graphql_points: int = 800
    budget_rest: int = 400
    force: bool = False
    settings: GitHubSettings = field(default_factory=GitHubSettings)
    _cache: dict[tuple[str, str], dict[str, Any]] = field(
        default_factory=dict, repr=False
    )
    _q_chunks: dict[str, list[dict[str, Any]]] = field(default_factory=dict, repr=False)
    _q_index: dict[str, int] = field(default_factory=dict, repr=False)

    def should_stop(self) -> bool:
        if self.graphql_used >= self.budget_graphql_points - 80:
            return True
        if self.graphql_remaining is not None and self.graphql_remaining < 80:
            return True
        return self.rest_used >= self.budget_rest

    def graphql(
        self, document: str, variables: dict | None = None, *, force: bool = False
    ) -> dict[str, Any]:
        variables = variables or {}
        op = operation_name(document)
        cache_key = (op, json.dumps(variables, sort_keys=True, default=str))
        skip_cache = force or self.force
        if not skip_cache and cache_key in self._cache:
            return self._cache[cache_key]
        if self.should_stop() and op != "HydrateANode":
            raise GitHubError(
                "budget",
                "GraphQL/REST budget exhausted",
                retryable=False,
                source=op,
            )
        self.graphql_network_calls += 1
        self.graphql_used += 1
        if self.graphql_remaining is not None:
            self.graphql_remaining = max(0, self.graphql_remaining - 1)
        body = self._dispatch(op, variables)
        self._cache[cache_key] = body
        return body

    def get(self, path: str, params: dict | None = None) -> FakeResponse:
        return self.request("GET", path, params=params)

    def request(self, method: str, url: str, **kw: Any) -> FakeResponse:
        method = method.upper()
        path = urlparse(url).path if "://" in url else url
        path = path if path.startswith("/") else "/" + path
        params = kw.get("params") or {}
        if method in {"GET", "HEAD"}:
            self.rest_used += 1
        return self._rest(method, path, params)

    def _dispatch(self, op: str, variables: dict[str, Any]) -> dict[str, Any]:
        rl = {
            "cost": 1,
            "remaining": self.graphql_remaining,
            "limit": 5000,
            "resetAt": "2026-08-24T01:00:00Z",
        }
        if op == "SearchRepos":
            q = str(variables.get("q") or "")
            n = int(variables.get("n") or 25)
            self.search_queries.append(q)
            chunk = self._chunk_for_q(q, n)
            total = (
                self.search_total_override
                if self.search_total_override is not None
                else len(chunk)
            )
            return {
                "data": {
                    "rateLimit": rl,
                    "search": {
                        "repositoryCount": total,
                        "pageInfo": {"hasNextPage": total > n},
                        "nodes": chunk[:n],
                    },
                }
            }
        if op in {
            "HydrateANode",
            "HydrateBNode",
            "HydrateBStripped",
            "HydrateA",
            "HydrateB",
        }:
            self.hydrate_calls += 1
            nid = variables.get("id")
            if op in {"HydrateA", "HydrateB"}:
                owner = variables.get("owner")
                name = variables.get("name")
                node = self._by_name(f"{owner}/{name}")
                nid = node.get("id") if node else None
            if nid:
                self.hydrate_ids.append(str(nid))
            if op in {"HydrateANode", "HydrateA"}:
                self.hydrate_a_calls += 1
            else:
                self.hydrate_b_calls += 1
            if nid in self.fail_ids:
                raise GitHubError(
                    "http_5xx",
                    "server error",
                    retryable=True,
                    status=500,
                    source=op,
                )
            if op in {"HydrateBNode", "HydrateB", "HydrateBStripped"} and (
                nid in self.b_missing
            ):
                raise GitHubError(
                    "http_404",
                    "Not Found",
                    retryable=False,
                    status=404,
                    source=op,
                )
            if nid is None or nid in self.missing or str(nid) not in self.nodes:
                raise GitHubError(
                    "http_404",
                    "Not Found",
                    retryable=False,
                    status=404,
                    source=op,
                )
            repo = dict(self.nodes[str(nid)])
            field = "repository" if op in {"HydrateA", "HydrateB"} else "node"
            return {"data": {"rateLimit": rl, field: repo}}
        raise AssertionError(f"unexpected GraphQL operation {op}")

    def _chunk_for_q(self, q: str, n: int) -> list[dict[str, Any]]:
        if q in self._q_chunks:
            return self._q_chunks[q]
        idx = len(self._q_index)
        self._q_index[q] = idx
        if self.search_pages is not None:
            chunk = self.search_pages[idx] if idx < len(self.search_pages) else []
        else:
            start = idx * n
            chunk = self.search_nodes[start : start + n]
        self._q_chunks[q] = chunk
        return chunk

    def _by_name(self, full_name: str) -> dict[str, Any] | None:
        for node in self.nodes.values():
            if node.get("nameWithOwner") == full_name:
                return node
        return None

    def _rest(self, method: str, path: str, params: dict[str, Any]) -> FakeResponse:
        parts = [p for p in path.split("/") if p]
        if parts[:2] == ["search", "repositories"]:
            return FakeResponse(
                200, {"total_count": 0, "incomplete_results": False, "items": []}
            )
        if len(parts) < 3 or parts[0] != "repos":
            return FakeResponse(404, {"message": "Not Found"})
        full = f"{parts[1]}/{parts[2]}"
        rest = parts[3:]
        kind = None
        if rest[:1] == ["contributors"]:
            kind = "contributors"
        elif rest[:1] == ["commits"]:
            kind = "commits"
        elif rest[:1] == ["contents"]:
            kind = "contents"
        elif rest[:2] == ["actions", "workflows"]:
            kind = "workflows"
        elif rest[:2] == ["community", "profile"]:
            kind = "community"
        status = self.rest_status.get((full, kind)) if kind else None
        if status in {403, 404, 410, 451, 500, 502, 503}:
            reason = "http_5xx" if status >= 500 else "http_404"
            raise GitHubError(
                reason,
                "rest error",
                retryable=status >= 500,
                status=status,
                source=f"/repos/{full}",
            )
        if status == 204:
            return FakeResponse(204)
        if rest[:1] == ["contributors"]:
            page = int(params.get("page") or 1)
            self.contributor_requests.append((full, page))
            pages = self.contributor_pages.get(full)
            if pages is not None:
                idx = page - 1
                rows = pages[idx] if 0 <= idx < len(pages) else []
                return FakeResponse(200, rows)
            return FakeResponse(200, self.contributors.get(full, []))
        if rest[:1] == ["commits"]:
            return FakeResponse(200, self.commits.get(full, []))
        if rest[:1] == ["releases"]:
            return FakeResponse(200, [])
        if rest[:1] == ["pulls"]:
            return FakeResponse(200, self.pulls.get(full, []))
        if rest[:1] == ["contents"]:
            extra = "/".join(rest[1:])
            listing = self.contents.get(
                full,
                [
                    {"name": "README.md", "type": "file"},
                    {"name": "src", "type": "dir"},
                    {"name": "pyproject.toml", "type": "file"},
                ],
            )
            if not extra:
                if method == "HEAD":
                    return FakeResponse(200)
                return FakeResponse(200, listing)
            names = {
                str(item.get("name")) for item in listing if isinstance(item, dict)
            }
            present = extra.split("/", 1)[0] in names
            if method == "HEAD":
                return FakeResponse(200 if present else 404)
            return FakeResponse(
                200 if present else 404, [] if present else {"message": "Not Found"}
            )
        if rest[:2] == ["actions", "workflows"]:
            return FakeResponse(
                200,
                self.workflows.get(
                    full, {"total_count": 1, "workflows": [{"name": "ci"}]}
                ),
            )
        if rest[:2] == ["community", "profile"]:
            return FakeResponse(
                200,
                self.community.get(
                    full,
                    {"health_percentage": 70, "files": {"contributing": None}},
                ),
            )
        return FakeResponse(404, {"message": "Not Found"})
