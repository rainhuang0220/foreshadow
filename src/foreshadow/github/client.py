from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, NoReturn, Self
from urllib.parse import urlparse

import httpx

from foreshadow import __version__
from foreshadow.clock import Clock
from foreshadow.config import GitHubSettings
from foreshadow.github.cache import HttpCache, graphql_cache_key, rest_cache_key
from foreshadow.github.queries import HYDRATE_B_STRIPPED

log = logging.getLogger("foreshadow.github")

_SECRET_RE = re.compile(
    r"(?i)(ghp_[A-Za-z0-9]+|gho_[A-Za-z0-9]+|ghu_[A-Za-z0-9]+|"
    r"ghs_[A-Za-z0-9]+|ghr_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|"
    r"Bearer\s+\S+)"
)
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_REQUIRED_REPO_PATHS = (
    ("id",),
    ("nameWithOwner",),
    ("stargazerCount",),
    ("forkCount",),
    ("isFork",),
    ("isArchived",),
    ("isDisabled",),
    ("isEmpty",),
    ("createdAt",),
    ("issuesOpen", "totalCount"),
    ("prsOpen", "totalCount"),
)
_FIVE_XX = frozenset({500, 502, 503, 504})
_NOT_FOUND = frozenset({404, 410, 451})
_BACKOFF = (1.0, 2.0, 4.0, 8.0)
_STRIPPED_WAIT_S = 5.0
_USER_AGENT = (
    f"foreshadow-radar/{__version__} (+https://github.com/rainhuang0220/foreshadow)"
)


class WriteAttemptError(RuntimeError):
    """REST write or GraphQL mutation attempted."""


class GitHubError(RuntimeError):
    def __init__(
        self,
        reason: str,
        detail: str = "",
        *,
        retryable: bool = False,
        status: int | None = None,
        source: str = "",
    ) -> None:
        self.reason = reason
        self.detail = redact(detail)
        self.retryable = retryable
        self.status = status
        self.source = source
        super().__init__(self.detail or reason)


@dataclass
class SourceFailure:
    source: str
    reason: str
    detail: str
    retryable: bool


def redact(text: str, extra: str | None = None) -> str:
    out = _SECRET_RE.sub("[REDACTED]", text)
    if extra and len(extra) >= 8:
        out = out.replace(extra, "[REDACTED]")
    out = re.sub(r"(?i)(authorization\s*[:=]\s*)(\S+)", r"\1[REDACTED]", out)
    return out


def resolve_token() -> str:
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()
    if shutil.which("gh"):
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            result = None
        if result is not None and result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    print("missing GitHub token", file=sys.stderr)
    raise SystemExit(2)


def graphql_marks_incomplete(payload: dict) -> bool:
    data = payload.get("data")
    if not isinstance(data, dict):
        return True
    if "search" in data and "repository" not in data and "node" not in data:
        return False
    repo = data.get("repository")
    if not isinstance(repo, dict):
        repo = data.get("node")
    if not isinstance(repo, dict):
        return True
    for path in _REQUIRED_REPO_PATHS:
        cur: Any = repo
        for key in path:
            if not isinstance(cur, dict) or key not in cur or cur[key] is None:
                return True
            cur = cur[key]
    return False


def _prepare_graphql(document: str) -> str:
    i = 0
    n = len(document)
    out: list[str] = []
    while i < n:
        if document.startswith('"""', i):
            j = document.find('"""', i + 3)
            if j == -1:
                break
            out.append(" ")
            i = j + 3
            continue
        ch = document[i]
        if ch == '"':
            i += 1
            while i < n:
                if document[i] == "\\":
                    i += 2
                    continue
                if document[i] == '"':
                    i += 1
                    break
                i += 1
            out.append('""')
            continue
        if ch == "#":
            while i < n and document[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _skip_braces(text: str, i: int) -> int:
    while i < len(text) and text[i] != "{":
        i += 1
    depth = 0
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def first_operation_token(document: str) -> str | None:
    text = _prepare_graphql(document)
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        if text[i] == "{":
            return "query"
        match = _IDENT_RE.match(text, i)
        if match is None:
            i += 1
            continue
        word = match.group(0)
        if word in {"query", "mutation", "subscription"}:
            return word
        if word == "fragment":
            i = _skip_braces(text, match.end())
            continue
        i = match.end()
    return None


def operation_name(document: str) -> str:
    text = _prepare_graphql(document)
    match = re.search(
        r"\b(?:query|mutation|subscription)\s+([A-Za-z_][A-Za-z0-9_]*)", text
    )
    if match:
        return match.group(1)
    return "anonymous"


def rest_path(url: str) -> str:
    raw = url if "://" in url else f"https://host/{url.lstrip('/')}"
    path = urlparse(raw).path
    path = re.sub(r"/+", "/", path)
    if len(path) > 1:
        path = path.rstrip("/")
    return path or "/"


def rest_path_denied(url: str) -> bool:
    parts = [p for p in rest_path(url).split("/") if p]
    if len(parts) >= 2 and parts[0] == "search" and parts[1] == "code":
        return True
    if len(parts) >= 3 and parts[0] == "repos":
        rest = parts[3:]
        if rest == ["stargazers"]:
            return True
        if rest and rest[0] == "subscribers":
            return True
        if rest and rest[0] == "traffic":
            return True
        if rest and rest[0] == "stats":
            return True
        if len(rest) >= 2 and rest[0] == "network" and rest[1] == "dependents":
            return True
    return False


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(int(raw)))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return max(0.0, (when.timestamp() - time.time()))


class GitHubClient:
    def __init__(
        self,
        token: str,
        transport: httpx.BaseTransport | None = None,
        *,
        settings: GitHubSettings | None = None,
        clock: Clock | None = None,
        cache: HttpCache | None = None,
        sleep: Callable[[float], None] | None = None,
        rng: random.Random | None = None,
        force: bool = False,
    ) -> None:
        self._token = token
        self.transport = transport
        self.settings = settings or GitHubSettings()
        self.clock = clock or Clock()
        self.cache = cache or HttpCache(clock=self.clock)
        self._sleep_fn = time.sleep if sleep is None else sleep
        self._rng = rng or random.Random()
        self.force = force
        self.graphql_used = 0
        self.graphql_remaining: int | None = None
        self.rest_used = 0
        self.source_failures: list[SourceFailure] = []
        self._client: httpx.Client | None = None
        self._last_search_at: float | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return "GitHubClient(token=***)"

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def should_stop(self) -> bool:
        cap = self.settings.budget_graphql_points
        if self.graphql_used >= cap - 80:
            return True
        if self.graphql_remaining is not None and self.graphql_remaining < 80:
            return True
        return self.rest_used >= self.settings.budget_rest

    def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        method = method.upper()
        if self._is_graphql_url(url):
            if method != "POST":
                raise WriteAttemptError(f"{method} GraphQL is not allowed")
            body = kw.get("json")
            doc = ""
            if isinstance(body, dict):
                doc = str(body.get("query") or "")
            self._assert_graphql_query(doc)
            return self._http_send(method, url, **kw)
        if method in _WRITE_METHODS:
            raise WriteAttemptError(f"{method} is not allowed")
        if method not in {"GET", "HEAD"}:
            raise WriteAttemptError(f"{method} is not allowed")
        self._assert_rest_allowed(url)
        return self._http_send(method, url, **kw)

    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        return self.request("GET", self._rest_url(path), params=params)

    def graphql(self, document: str, variables: dict, *, force: bool = False) -> dict:
        self._assert_graphql_query(document)
        key = graphql_cache_key(document, variables or {})
        skip_cache = force or self.force
        if not skip_cache:
            hit = self.cache.get_graphql(key)
            if hit is not None:
                return hit
        if self.should_stop():
            self._fail(
                "budget",
                "GraphQL/REST budget exhausted",
                retryable=False,
                source=operation_name(document),
            )
        if self._is_search_query(document):
            self._space_search()
        log.debug("graphql %s", operation_name(document))
        try:
            body = self._graphql_post(document, variables or {})
        except GitHubError as exc:
            if self._should_strip_fallback(document, variables or {}, exc):
                self._sleep_fn(_STRIPPED_WAIT_S)
                body = self._graphql_post(
                    HYDRATE_B_STRIPPED, {"id": (variables or {})["id"]}
                )
            else:
                raise
        self.cache.put_graphql(key, body)
        return body

    def _graphql_post(self, document: str, variables: dict) -> dict:
        resp = self._http_send(
            "POST",
            self.settings.graphql_url,
            json={"query": document, "variables": variables},
            is_graphql=True,
        )
        try:
            body = resp.json()
        except json.JSONDecodeError:
            self._fail(
                "decode",
                resp.text,
                retryable=False,
                status=resp.status_code,
                source=operation_name(document),
            )
        if not isinstance(body, dict):
            self._fail(
                "decode",
                resp.text,
                retryable=False,
                status=resp.status_code,
                source=operation_name(document),
            )
        self._account_graphql(body, resp)
        errors = body.get("errors")
        if body.get("data") is None and errors:
            self.source_failures.append(
                SourceFailure(
                    source=operation_name(document),
                    reason="graphql_error",
                    detail=redact(
                        json.dumps(errors, ensure_ascii=False), extra=self._token
                    ),
                    retryable=False,
                )
            )
        return body

    def _http_send(
        self,
        method: str,
        url: str,
        *,
        is_graphql: bool = False,
        **kw: Any,
    ) -> httpx.Response:
        headers = dict(kw.pop("headers", None) or {})
        rest_key: str | None = None
        if method in {"GET", "HEAD"} and not is_graphql:
            if self._is_search_path(url):
                self._space_search()
            rest_key = rest_cache_key(url, kw.get("params"))
            etag = self.cache.get_etag(rest_key)
            if etag:
                headers["If-None-Match"] = etag
            if self.should_stop():
                self._fail(
                    "budget",
                    "GraphQL/REST budget exhausted",
                    retryable=False,
                    source=url,
                )
        if headers:
            kw["headers"] = headers

        attempts = 0
        max_retries = self.settings.max_retries
        while True:
            try:
                resp = self._http().request(method, url, **kw)
            except httpx.TimeoutException as exc:
                self._fail("timeout", str(exc), retryable=True, source=url)
            except httpx.RequestError as exc:
                if attempts < 2:
                    self._sleep_fn(self._backoff(attempts, None))
                    attempts += 1
                    continue
                self._fail("timeout", str(exc), retryable=True, source=url)

            if resp.status_code in _NOT_FOUND:
                self._fail(
                    "http_404",
                    resp.text,
                    retryable=False,
                    status=resp.status_code,
                    source=url,
                )
            if resp.status_code == 304:
                return resp
            if self._is_rate_limited(resp):
                remaining = resp.headers.get("x-ratelimit-remaining")
                if resp.status_code == 403 and remaining == "0":
                    self._fail(
                        "rate_limit",
                        resp.text,
                        retryable=False,
                        status=403,
                        source=url,
                    )
                if attempts >= max_retries:
                    self._fail(
                        "rate_limit",
                        resp.text,
                        retryable=True,
                        status=resp.status_code,
                        source=url,
                    )
                self._sleep_fn(self._backoff(attempts, _retry_after_seconds(resp)))
                attempts += 1
                continue
            if resp.status_code in _FIVE_XX:
                if attempts < 2:
                    self._sleep_fn(self._backoff(attempts, None))
                    attempts += 1
                    continue
                self._fail(
                    "http_5xx",
                    resp.text,
                    retryable=True,
                    status=resp.status_code,
                    source=url,
                )
            if resp.status_code >= 400:
                reason = "http_5xx" if resp.status_code >= 500 else "http_404"
                self._fail(
                    reason,
                    resp.text,
                    retryable=resp.status_code >= 500,
                    status=resp.status_code,
                    source=url,
                )
            if method in {"GET", "HEAD"} and not is_graphql:
                self.rest_used += 1
                etag = resp.headers.get("ETag")
                if etag and rest_key is not None:
                    self.cache.put_rest(rest_key, etag, resp.content)
            return resp

    def _http(self) -> httpx.Client:
        if self._client is None:
            kwargs: dict[str, Any] = {
                "headers": self._headers(),
                "timeout": self.settings.timeout_seconds,
                "follow_redirects": True,
            }
            if self.transport is not None:
                kwargs["transport"] = self.transport
            self._client = httpx.Client(**kwargs)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": self.settings.api_version,
            "User-Agent": _USER_AGENT,
        }

    def _rest_url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return self.settings.api_url.rstrip("/") + "/" + path.lstrip("/")

    def _is_graphql_url(self, url: str) -> bool:
        target = self.settings.graphql_url.rstrip("/")
        base = url.split("?", 1)[0].rstrip("/")
        if base == target:
            return True
        return urlparse(url).path.rstrip("/") == "/graphql"

    def _assert_graphql_query(self, document: str) -> None:
        token = first_operation_token(document)
        if token != "query":
            raise WriteAttemptError("GraphQL mutation is not allowed")

    def _assert_rest_allowed(self, url: str) -> None:
        if rest_path_denied(url):
            raise WriteAttemptError(f"GET {rest_path(url)} is not allowed")

    def _is_search_query(self, document: str) -> bool:
        if operation_name(document) == "SearchRepos":
            return True
        return "search(" in _prepare_graphql(document) and "REPOSITORY" in document

    def _is_search_path(self, url: str) -> bool:
        parts = [p for p in rest_path(url).split("/") if p]
        return bool(parts) and parts[0] == "search"

    def _is_hydrate_b(self, document: str) -> bool:
        return operation_name(document) in {"HydrateB", "HydrateBNode"}

    def _is_stripped(self, document: str) -> bool:
        return operation_name(document) == "HydrateBStripped"

    def _should_strip_fallback(
        self, document: str, variables: dict, exc: GitHubError
    ) -> bool:
        if exc.reason not in {"http_5xx", "timeout"}:
            return False
        if not self._is_hydrate_b(document) or self._is_stripped(document):
            return False
        return bool(variables.get("id"))

    def _space_search(self) -> None:
        spacing = self.settings.search_spacing_ms / 1000.0
        if spacing <= 0:
            self._last_search_at = time.monotonic()
            return
        now = time.monotonic()
        if self._last_search_at is not None:
            wait = spacing - (now - self._last_search_at)
            if wait > 0:
                self._sleep_fn(wait)
        self._last_search_at = time.monotonic()

    def _account_graphql(self, body: dict, resp: httpx.Response) -> None:
        data = body.get("data")
        rl = data.get("rateLimit") if isinstance(data, dict) else None
        cost = 1
        remaining = None
        if isinstance(rl, dict):
            if rl.get("cost") is not None:
                try:
                    cost = int(rl["cost"])
                except (TypeError, ValueError):
                    cost = 1
            if rl.get("remaining") is not None:
                try:
                    remaining = int(rl["remaining"])
                except (TypeError, ValueError):
                    remaining = None
        if remaining is None:
            hdr = resp.headers.get("x-ratelimit-remaining")
            if hdr:
                try:
                    remaining = int(hdr)
                except ValueError:
                    remaining = None
        self.graphql_used += cost
        if remaining is not None:
            self.graphql_remaining = remaining

    def _is_rate_limited(self, resp: httpx.Response) -> bool:
        if resp.status_code == 429:
            return True
        if resp.status_code != 403:
            return False
        remaining = resp.headers.get("x-ratelimit-remaining")
        try:
            if remaining is not None and int(remaining) > 0:
                return True
        except ValueError:
            pass
        text = (resp.text or "").lower()
        return "rate limit" in text or "secondary rate" in text or "abuse" in text

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return retry_after
        base = _BACKOFF[min(attempt, len(_BACKOFF) - 1)]
        return base + self._rng.uniform(0, 0.25)

    def _fail(
        self,
        reason: str,
        detail: str,
        *,
        retryable: bool,
        status: int | None = None,
        source: str = "",
    ) -> NoReturn:
        redacted = redact(detail, extra=self._token)
        self.source_failures.append(
            SourceFailure(
                source=source,
                reason=reason,
                detail=redacted,
                retryable=retryable,
            )
        )
        raise GitHubError(
            reason,
            redacted,
            retryable=retryable,
            status=status,
            source=source,
        )
