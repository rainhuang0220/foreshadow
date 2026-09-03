import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from foreshadow.clock import Clock
from foreshadow.config import GitHubSettings
from foreshadow.github.client import GitHubClient, WriteAttemptError, resolve_token
from foreshadow.github.queries import (
    HYDRATE_A,
    HYDRATE_A_NODE,
    HYDRATE_B,
    HYDRATE_B_NODE,
    HYDRATE_B_STRIPPED,
    SEARCH_REPOS,
)
from foreshadow.github.rest import (
    content_exists,
    fetch_closed_pulls,
    fetch_contributors,
    fetch_issue,
    fetch_root_contents,
)

FIXTURES = Path(__file__).parent / "fixtures"
HYDRATE_A_JSON = FIXTURES / "graphql" / "hydrate_a.json"
CONTRIBUTORS_JSON = FIXTURES / "rest" / "contributors.json"

DOCUMENTS = {
    "SEARCH_REPOS": SEARCH_REPOS,
    "HYDRATE_A": HYDRATE_A,
    "HYDRATE_A_NODE": HYDRATE_A_NODE,
    "HYDRATE_B": HYDRATE_B,
    "HYDRATE_B_NODE": HYDRATE_B_NODE,
    "HYDRATE_B_STRIPPED": HYDRATE_B_STRIPPED,
}

CONNECTION_FIELDS = (
    "search",
    "repositoryTopics",
    "issues",
    "pullRequests",
    "discussions",
    "labels",
    "comments",
    "assignees",
    "repositories",
    "releases",
)


def _gql_ok(extra: dict | None = None, *, cost: int = 1, remaining: int = 5000) -> dict:
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


def test_rest_post_raises_before_socket():
    c = GitHubClient(token="x", transport=None)  # no real transport
    with pytest.raises(WriteAttemptError):
        c.request("POST", "https://api.github.com/repos/a/b/issues", json={})


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_rest_writes_raise_before_socket(method: str):
    c = GitHubClient(token="x", transport=None)
    with pytest.raises(WriteAttemptError):
        c.request(method, "https://api.github.com/repos/a/b/issues/1", json={})


def test_mutation_document_rejected():
    c = GitHubClient(token="x")
    with pytest.raises(WriteAttemptError):
        c.graphql(
            'mutation { addStar(input:{starrableId:"x"}) { clientMutationId } }', {}
        )


def test_commented_mutation_still_rejected():
    c = GitHubClient(token="x")
    doc = '''
    # not a query
    """ this mentions mutation """
    mutation AddStar { addStar(input:{starrableId:"x"}) { clientMutationId } }
    '''
    with pytest.raises(WriteAttemptError):
        c.graphql(doc, {})


def test_word_mutation_in_description_allowed(respx_mock):
    respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(
            200, json={"data": {"search": {"repositoryCount": 0}}}
        )
    )
    c = GitHubClient(token="x")
    doc = 'query Q { search(query: "mutation", type: REPOSITORY, first: 1) { repositoryCount } }'
    c.graphql(doc, {})  # must not raise WriteAttemptError


def test_stargazers_list_denied_count_allowed(respx_mock):
    c = GitHubClient(token="x")
    with pytest.raises(WriteAttemptError):
        c.get("/repos/a/b/stargazers")
    respx_mock.get("https://api.github.com/repos/a/b/stargazers/count").mock(
        return_value=httpx.Response(200, json={"stars": 1})
    )
    assert c.get("/repos/a/b/stargazers/count").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/repos/a/b/subscribers",
        "/repos/a/b/traffic",
        "/repos/a/b/traffic/views",
        "/repos/a/b/stats/contributors",
        "/repos/a/b/network/dependents",
        "/search/code",
    ],
)
def test_denied_rest_paths(path: str):
    c = GitHubClient(token="x", transport=None)
    with pytest.raises(WriteAttemptError):
        c.get(path)


def test_search_repositories_allowed(respx_mock):
    respx_mock.get("https://api.github.com/search/repositories").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    c = GitHubClient(token="x")
    assert (
        c.get(
            "/search/repositories", params={"q": "memkit", "per_page": 25}
        ).status_code
        == 200
    )


def test_head_allowed(respx_mock):
    respx_mock.head("https://api.github.com/repos/a/b/contents/src").mock(
        return_value=httpx.Response(200)
    )
    c = GitHubClient(token="x")
    r = c.request("HEAD", "https://api.github.com/repos/a/b/contents/src")
    assert r.status_code == 200


def test_contents_head_404_is_absent(respx_mock):
    route = respx_mock.head("https://api.github.com/repos/a/b/contents/tests").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    c = GitHubClient(token="x")
    assert content_exists(c, "a", "b", "tests") is False
    assert route.call_count == 1
    assert c.source_failures == []


def test_documents_have_first_and_no_watchers():
    conn_re = re.compile(
        r"\b(" + "|".join(CONNECTION_FIELDS) + r")\s*\(",
    )
    for name, doc in DOCUMENTS.items():
        assert re.search(r"\bwatchers\b", doc) is None, name
        assert "rateLimit" in doc, name
        for match in conn_re.finditer(doc):
            depth = 0
            end = None
            for i, ch in enumerate(doc[match.end() - 1 :], start=match.end() - 1):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            assert end is not None, f"{name} unclosed {match.group(0)}"
            args = doc[match.end() : end]
            assert "first:" in args.replace(" ", ""), (
                f"{name} {match.group(1)} missing first:"
            )


def test_hydrate_a_fixture_roundtrip(respx_mock):
    payload = json.loads(HYDRATE_A_JSON.read_text(encoding="utf-8"))
    respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(200, json=payload)
    )
    c = GitHubClient(token="x")
    out = c.graphql(HYDRATE_A, {"owner": "acme", "name": "memkit"})
    repo = out["data"]["repository"]
    assert "watchers" not in repo
    assert repo["stargazerCount"] == 900
    assert repo["issuesOpen"]["totalCount"] == 12


def test_force_skips_same_day_graphql_cache(respx_mock, frozen_clock):
    route = respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(200, json=_gql_ok())
    )
    c = GitHubClient(token="x", clock=frozen_clock)
    doc = "query { rateLimit { cost remaining limit resetAt } }"
    c.graphql(doc, {})
    c.graphql(doc, {})
    assert route.call_count == 1
    c.graphql(doc, {}, force=True)
    assert route.call_count == 2


def test_rest_etag_304_does_not_consume_budget(respx_mock):
    url = "https://api.github.com/repos/a/b/contents"
    payload = [{"name": "README.md"}]
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json=payload, headers={"ETag": '"abc"'})
        return httpx.Response(304, headers={"ETag": '"abc"'})

    respx_mock.get(url).mock(side_effect=handler)
    c = GitHubClient(token="x")
    assert c.get("/repos/a/b/contents").status_code == 200
    assert c.rest_used == 1
    r2 = c.get("/repos/a/b/contents")
    assert r2.status_code == 304
    assert r2.json() == payload
    assert c.rest_used == 1
    assert respx_mock.calls[1].request.headers["If-None-Match"] == '"abc"'
    assert fetch_root_contents(c, "a", "b") == payload
    assert c.rest_used == 1


def test_force_still_sends_rest_etag(respx_mock, frozen_clock):
    url = "https://api.github.com/repos/a/b/contents"
    respx_mock.get(url).mock(
        side_effect=[
            httpx.Response(
                200, json=[{"name": "README.md"}], headers={"ETag": '"abc"'}
            ),
            httpx.Response(304, headers={"ETag": '"abc"'}),
        ]
    )
    c = GitHubClient(token="x", clock=frozen_clock, force=True)
    c.get("/repos/a/b/contents")
    c.get("/repos/a/b/contents")
    assert respx_mock.calls[1].request.headers["If-None-Match"] == '"abc"'


def test_required_headers(respx_mock):
    route = respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(200, json=_gql_ok())
    )
    c = GitHubClient(token="secret-token")
    c.graphql("query { rateLimit { cost remaining limit resetAt } }", {})
    headers = route.calls.last.request.headers
    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2026-03-10"
    assert "foreshadow-radar/" in headers["User-Agent"]
    assert "rainhuang0220/foreshadow" in headers["User-Agent"]


def test_graphql_cost_from_rate_limit(respx_mock):
    respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(200, json=_gql_ok(cost=12, remaining=90))
    )
    c = GitHubClient(token="x")
    c.graphql(SEARCH_REPOS, {"q": "memkit", "n": 1})
    assert c.graphql_used == 12
    assert c.graphql_remaining == 90
    assert not c.should_stop()


def test_search_spacing_ms(respx_mock):
    respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(
            200,
            json=_gql_ok(
                {
                    "search": {
                        "repositoryCount": 0,
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [],
                    }
                }
            ),
        )
    )
    sleeps: list[float] = []
    c = GitHubClient(
        token="x",
        settings=GitHubSettings(search_spacing_ms=2000),
        sleep=sleeps.append,
    )
    c.graphql(SEARCH_REPOS, {"q": "a", "n": 1})
    c.graphql(SEARCH_REPOS, {"q": "b", "n": 1})
    assert sleeps
    assert sleeps[0] == pytest.approx(2.0, abs=0.05)


def test_resolve_token_env_order(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "from-github")
    monkeypatch.setenv("GH_TOKEN", "from-gh")
    assert resolve_token() == "from-github"
    monkeypatch.delenv("GITHUB_TOKEN")
    assert resolve_token() == "from-gh"


def test_resolve_token_gh_auth_not_printed(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(
        "foreshadow.github.client.shutil.which",
        lambda cmd: "/usr/bin/gh" if cmd == "gh" else None,
    )

    class Result:
        returncode = 0
        stdout = "gho_fromcli\n"
        stderr = "do-not-print\n"

    monkeypatch.setattr(
        "foreshadow.github.client.subprocess.run", lambda *a, **k: Result()
    )
    assert resolve_token() == "gho_fromcli"
    captured = capsys.readouterr()
    assert "gho_fromcli" not in captured.out
    assert "gho_fromcli" not in captured.err


def test_resolve_token_missing_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr("foreshadow.github.client.shutil.which", lambda cmd: None)
    with pytest.raises(SystemExit) as ei:
        resolve_token()
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert "GITHUB_TOKEN" in err
    assert "gh auth" in err.lower()


def test_contributors_fixture_k18(respx_mock):
    rows = json.loads(CONTRIBUTORS_JSON.read_text(encoding="utf-8"))
    route = respx_mock.get(
        "https://api.github.com/repos/acme/memkit/contributors"
    ).mock(return_value=httpx.Response(200, json=rows))
    c = GitHubClient(token="x")
    got = fetch_contributors(c, "acme", "memkit")
    assert [r.get("login") or r.get("name") for r in got] == [
        "alice",
        "bob",
        "dependabot[bot]",
        "Anon",
    ]
    assert route.call_count == 1


def test_same_day_cache_uses_clock(respx_mock):
    route = respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(200, json=_gql_ok())
    )
    clock = Clock(now=datetime(2026, 8, 24, 0, 5, tzinfo=UTC))
    c = GitHubClient(token="x", clock=clock)
    doc = "query { rateLimit { cost remaining limit resetAt } }"
    c.graphql(doc, {"n": 1})
    clock._now = datetime(2026, 8, 25, 0, 5, tzinfo=UTC)
    c.graphql(doc, {"n": 1})
    assert route.call_count == 2


def test_issue_and_pulls_are_get_only(respx_mock):
    issue_url = "https://api.github.com/repos/acme/toy/issues/73"
    pulls_url = "https://api.github.com/repos/acme/toy/pulls"
    respx_mock.get(issue_url).mock(
        return_value=httpx.Response(
            200, json={"number": 73, "title": "crash", "body": "x"}
        )
    )
    respx_mock.get(pulls_url).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "merged_at": "2026-08-01T00:00:00Z",
                    "author_association": "CONTRIBUTOR",
                }
            ],
        )
    )
    c = GitHubClient(token="x")
    issue = fetch_issue(c, "acme", "toy", 73)
    pulls = fetch_closed_pulls(c, "acme", "toy")
    assert issue and issue["number"] == 73
    assert len(pulls) == 1
    assert all(call.request.method == "GET" for call in respx_mock.calls)
