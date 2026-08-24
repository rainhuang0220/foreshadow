import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from foreshadow.clock import Clock

REPO_FIXTURES = Path(__file__).parent / "fixtures" / "repos"


def load_repo_fixture(name: str) -> dict:
    return json.loads((REPO_FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def repo_fixture():
    return load_repo_fixture


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("FORESHADOW_HOME", str(home))
    return home


@pytest.fixture
def frozen_clock():
    return Clock(now=datetime(2026, 8, 24, 0, 5, tzinfo=UTC))


@pytest.fixture
def fake_github(tmp_home, monkeypatch):
    from fakes import FakeGitHub, repo_node

    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    memkit = repo_node("R_memkit", "acme/memkit")
    other = repo_node("R_other", "acme/other")
    gh = FakeGitHub(
        nodes={"R_memkit": memkit, "R_other": other},
        search_nodes=[memkit, other],
        contributors={
            "acme/memkit": [
                {"login": "alice", "type": "User"},
                {"login": "bob", "type": "User"},
            ],
            "acme/other": [{"login": "carol", "type": "User"}],
        },
    )
    monkeypatch.setattr(
        "foreshadow.github.client.GitHubClient",
        lambda *a, **k: gh,
    )
    return gh
