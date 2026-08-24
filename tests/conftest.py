from datetime import UTC, datetime

import pytest

from foreshadow.clock import Clock


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("FORESHADOW_HOME", str(home))
    return home


@pytest.fixture
def frozen_clock():
    return Clock(now=datetime(2026, 8, 24, 0, 5, tzinfo=UTC))
