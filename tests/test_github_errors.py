import json
import logging

import httpx
import pytest

from foreshadow.config import GitHubSettings
from foreshadow.github.client import (
    GitHubClient,
    GitHubError,
    graphql_marks_incomplete,
)
from foreshadow.github.queries import HYDRATE_B_NODE, HYDRATE_B_STRIPPED

TOKEN = "ghp_abcdefghijklmnopqrstuvwxyz012345"


def _gql_ok(*, cost: int = 1, remaining: int = 5000, extra: dict | None = None) -> dict:
    data = {
        "rateLimit": {
            "cost": cost,
            "remaining": remaining,
            "limit": 5000,
            "resetAt": "2026-08-24T01:00:00Z",
        }
    }
    if extra:
        data.update(extra)
    return {"data": data}


def _required_repo() -> dict:
    return {
        "id": "R_1",
        "nameWithOwner": "a/b",
        "stargazerCount": 10,
        "forkCount": 1,
        "isFork": False,
        "isArchived": False,
        "isDisabled": False,
        "isEmpty": False,
        "createdAt": "2026-01-01T00:00:00Z",
        "issuesOpen": {"totalCount": 2},
        "prsOpen": {"totalCount": 1},
        "discussions": None,
    }


def test_404_is_not_retried(respx_mock):
    route = respx_mock.get("https://api.github.com/repos/a/b").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    c = GitHubClient(token="x", sleep=lambda _: None)
    with pytest.raises(GitHubError) as ei:
        c.get("/repos/a/b")
    assert ei.value.reason == "http_404"
    assert ei.value.status == 404
    assert route.call_count == 1
    assert c.source_failures
    assert c.source_failures[-1].reason == "http_404"


@pytest.mark.parametrize("status", [410, 451])
def test_gone_and_legal_are_not_found(respx_mock, status: int):
    respx_mock.get("https://api.github.com/repos/a/b").mock(
        return_value=httpx.Response(status, json={"message": "gone"})
    )
    c = GitHubClient(token="x", sleep=lambda _: None)
    with pytest.raises(GitHubError) as ei:
        c.get("/repos/a/b")
    assert ei.value.reason == "http_404"
    assert ei.value.status == status


def test_429_retries_then_source_failure(respx_mock):
    route = respx_mock.get("https://api.github.com/repos/a/b").mock(
        return_value=httpx.Response(429, json={"message": "rate limit"})
    )
    sleeps: list[float] = []
    c = GitHubClient(token="x", sleep=sleeps.append)
    with pytest.raises(GitHubError) as ei:
        c.get("/repos/a/b")
    assert ei.value.reason == "rate_limit"
    assert route.call_count == 1 + c.settings.max_retries
    assert len(sleeps) == c.settings.max_retries
    assert any(f.reason == "rate_limit" for f in c.source_failures)


def test_403_permission_is_not_retried(respx_mock):
    route = respx_mock.get("https://api.github.com/repos/a/b").mock(
        return_value=httpx.Response(
            403,
            headers={"X-RateLimit-Remaining": "4000"},
            json={"message": "Resource not accessible by integration"},
        )
    )
    sleeps: list[float] = []
    c = GitHubClient(token="x", sleep=sleeps.append)
    with pytest.raises(GitHubError) as ei:
        c.get("/repos/a/b")
    assert ei.value.status == 403
    assert ei.value.reason != "rate_limit"
    assert route.call_count == 1
    assert sleeps == []


def test_403_primary_remaining_zero_no_retry(respx_mock):
    route = respx_mock.get("https://api.github.com/repos/a/b").mock(
        return_value=httpx.Response(
            403,
            headers={"X-RateLimit-Remaining": "0"},
            json={"message": "API rate limit exceeded"},
        )
    )
    c = GitHubClient(token="x", sleep=lambda _: None)
    with pytest.raises(GitHubError) as ei:
        c.get("/repos/a/b")
    assert ei.value.reason == "rate_limit"
    assert ei.value.retryable is False
    assert route.call_count == 1


def test_403_retry_after_then_success(respx_mock):
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                403,
                headers={"Retry-After": "0", "X-RateLimit-Remaining": "4000"},
                json={"message": "You have exceeded a secondary rate limit"},
            )
        return httpx.Response(200, json={"ok": True})

    respx_mock.get("https://api.github.com/repos/a/b").mock(side_effect=handler)
    c = GitHubClient(token="x", sleep=lambda _: None)
    r = c.get("/repos/a/b")
    assert r.status_code == 200
    assert calls["n"] == 2


def test_502_retries_hydrate_b_stripped(respx_mock):
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        queries.append(body["query"])
        if "HydrateBStripped" in body["query"]:
            return httpx.Response(
                200,
                json=_gql_ok(extra={"node": _required_repo()}),
            )
        return httpx.Response(502, text="Bad Gateway")

    respx_mock.post("https://api.github.com/graphql").mock(side_effect=handler)
    sleeps: list[float] = []
    c = GitHubClient(token="x", sleep=sleeps.append)
    out = c.graphql(HYDRATE_B_NODE, {"id": "R_1"})
    assert out["data"]["node"]["id"] == "R_1"
    assert any("HydrateBStripped" in q for q in queries)
    assert any("HydrateBNode" in q or "query HydrateBNode" in q for q in queries)
    assert HYDRATE_B_STRIPPED.split()[0]  # document exists
    assert 5.0 in sleeps or any(s >= 5 for s in sleeps)


def test_token_never_in_failure_detail(respx_mock):
    respx_mock.get("https://api.github.com/repos/a/b").mock(
        return_value=httpx.Response(
            404,
            json={"message": f"Not Found token={TOKEN}"},
        )
    )
    c = GitHubClient(token=TOKEN, sleep=lambda _: None)
    with pytest.raises(GitHubError) as ei:
        c.get("/repos/a/b")
    assert "ghp_" not in ei.value.detail
    assert "github_pat_" not in ei.value.detail
    assert TOKEN not in ei.value.detail
    assert TOKEN not in str(ei.value)
    for failure in c.source_failures:
        assert "ghp_" not in failure.detail
        assert "github_pat_" not in failure.detail
        assert TOKEN not in failure.detail


def test_token_never_in_graphql_error_logs(respx_mock, caplog):
    caplog.set_level(logging.DEBUG)
    respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": None,
                "errors": [
                    {"message": f"bad {TOKEN} github_pat_abcdefghijklmnopqrstuv"}
                ],
            },
        )
    )
    c = GitHubClient(token=TOKEN, sleep=lambda _: None)
    c.graphql("query Q { rateLimit { cost remaining limit resetAt } }", {})
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "ghp_" not in blob
    assert "github_pat_" not in blob
    assert TOKEN not in blob
    assert "Q" in blob or "rateLimit" in blob or blob == "" or "graphql" in blob.lower()
    for failure in c.source_failures:
        assert "ghp_" not in failure.detail
        assert TOKEN not in failure.detail


def test_optional_graphql_errors_do_not_mark_incomplete():
    payload = {
        "data": {
            "rateLimit": {
                "cost": 1,
                "remaining": 100,
                "limit": 5000,
                "resetAt": "t",
            },
            "repository": {**_required_repo(), "discussions": None},
        },
        "errors": [
            {
                "path": ["repository", "discussions"],
                "message": "Field 'discussions' is restricted",
            }
        ],
    }
    assert graphql_marks_incomplete(payload) is False


def test_required_field_error_marks_incomplete():
    repo = _required_repo()
    del repo["stargazerCount"]
    payload = {
        "data": {"repository": repo},
        "errors": [
            {
                "path": ["repository", "stargazerCount"],
                "message": "Could not resolve",
            }
        ],
    }
    assert graphql_marks_incomplete(payload) is True


def test_budget_stop_when_remaining_below_80(respx_mock):
    route = respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(200, json=_gql_ok(remaining=79))
    )
    c = GitHubClient(token="x")
    c.graphql("query { rateLimit { cost remaining limit resetAt } }", {})
    assert c.should_stop()
    with pytest.raises(GitHubError) as ei:
        c.graphql("query { viewer { login } }", {})
    assert ei.value.reason == "budget"
    assert route.call_count == 1
    assert any(f.reason == "budget" for f in c.source_failures)


def test_rest_budget_cap(respx_mock):
    respx_mock.get("https://api.github.com/repos/a/b").mock(
        return_value=httpx.Response(200, json={})
    )
    respx_mock.get("https://api.github.com/repos/a/c").mock(
        return_value=httpx.Response(200, json={})
    )
    respx_mock.get("https://api.github.com/repos/a/d").mock(
        return_value=httpx.Response(200, json={})
    )
    c = GitHubClient(token="x", settings=GitHubSettings(budget_rest=2))
    c.get("/repos/a/b")
    c.get("/repos/a/c")
    with pytest.raises(GitHubError) as ei:
        c.get("/repos/a/d")
    assert ei.value.reason == "budget"


def test_decode_error_is_source_failure(respx_mock):
    respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(200, text="not-json{")
    )
    c = GitHubClient(token="x", sleep=lambda _: None)
    with pytest.raises(GitHubError) as ei:
        c.graphql("query { rateLimit { remaining } }", {})
    assert ei.value.reason == "decode"
    assert c.source_failures[-1].reason == "decode"
