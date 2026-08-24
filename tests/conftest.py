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
