"""Distribution artifacts. Catches the v0.2.1 duplicate-wheel install failure."""

from __future__ import annotations

import collections
import os
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

from foreshadow import __version__
from foreshadow.db import MIGRATIONS, SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_WHEEL_FILES = (
    *(f"foreshadow/sql/{name}" for _, name in MIGRATIONS),
    "foreshadow/directions.toml",
    "foreshadow/board/assets/board-bg.jpg",
    "foreshadow/__init__.py",
    "foreshadow/cli.py",
)


def test_pyproject_does_not_force_include_package_data():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.hatch.build.targets.wheel.force-include]" not in text


def test_project_version_matches_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__


@pytest.fixture(scope="module")
def built_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--out-dir", str(out)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return out


def _wheel(dist: Path) -> Path:
    wheels = list(dist.glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


def test_sdist_and_wheel_build(built_dist: Path):
    assert list(built_dist.glob("*.whl"))
    assert list(built_dist.glob("*.tar.gz"))


def test_wheel_resources_unique_and_present(built_dist: Path):
    wheel = _wheel(built_dist)
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    counts = collections.Counter(names)
    dups = sorted(name for name, n in counts.items() if n > 1)
    assert dups == [], dups
    missing = [name for name in REQUIRED_WHEEL_FILES if counts[name] != 1]
    assert missing == [], missing
    assert wheel.name.startswith(f"foreshadow_radar-{__version__}-")


def test_sdist_contains_runtime_resources(built_dist: Path):
    sdists = list(built_dist.glob("*.tar.gz"))
    assert len(sdists) == 1
    with tarfile.open(sdists[0], "r:gz") as tf:
        names = tf.getnames()
    prefix = f"foreshadow_radar-{__version__}"
    for rel in (
        "src/foreshadow/sql/001_init.sql",
        f"src/foreshadow/sql/{MIGRATIONS[-1][1]}",
        "src/foreshadow/directions.toml",
        "src/foreshadow/board/assets/board-bg.jpg",
    ):
        assert f"{prefix}/{rel}" in names, rel


def test_runtime_package_resources_load():
    import importlib.resources

    root = importlib.resources.files("foreshadow")
    first = root.joinpath("sql/001_init.sql").read_text(encoding="utf-8")
    latest = root.joinpath(f"sql/{MIGRATIONS[-1][1]}").read_text(encoding="utf-8")
    assert "CREATE TABLE" in first
    assert "CREATE TABLE" in latest
    directions = root.joinpath("directions.toml").read_text(encoding="utf-8")
    assert "[" in directions
    jpg = root.joinpath("board/assets/board-bg.jpg").read_bytes()
    assert len(jpg) > 100
    assert SCHEMA_VERSION == MIGRATIONS[-1][0]


def test_clean_wheel_install_cli_and_init(built_dist: Path, tmp_path: Path):
    wheel = _wheel(built_dist)
    venv = tmp_path / "venv"
    home = tmp_path / "home"
    home.mkdir()
    subprocess.run(
        ["uv", "venv", str(venv), "--python", sys.executable],
        check=True,
        capture_output=True,
        text=True,
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    foreshadow = venv / (
        "Scripts/foreshadow.exe" if os.name == "nt" else "bin/foreshadow"
    )
    subprocess.run(
        ["uv", "pip", "install", str(wheel), "--python", str(python)],
        check=True,
        capture_output=True,
        text=True,
    )
    env = os.environ.copy()
    env["FORESHADOW_HOME"] = str(home)
    env["HOME"] = str(home)
    env.pop("GITHUB_TOKEN", None)
    env.pop("GH_TOKEN", None)
    env.pop("FORESHADOW_CONFIG", None)
    version = subprocess.run(
        [str(foreshadow), "--version"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert __version__ in version.stdout
    help_out = subprocess.run(
        [str(foreshadow), "--help"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert help_out.returncode == 0
    assert "init" in help_out.stdout
    doctor = subprocess.run(
        [str(foreshadow), "doctor"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert "Traceback" not in doctor.stdout
    assert "Traceback" not in doctor.stderr
    combined = doctor.stdout + doctor.stderr
    assert "token" in combined.lower() or "GITHUB_TOKEN" in combined
    init = subprocess.run(
        [str(foreshadow), "init"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert "Foreshadow is ready" in init.stdout
    assert (home / "foreshadow.sqlite3").is_file()
    resource = subprocess.run(
        [
            str(python),
            "-c",
            (
                "from importlib.resources import files; "
                "root = files('foreshadow'); "
                "assert root.joinpath('sql/001_init.sql').read_text(); "
                "assert root.joinpath('directions.toml').read_text(); "
                "assert root.joinpath('board/assets/board-bg.jpg').read_bytes(); "
                "print('resources-ok')"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert "resources-ok" in resource.stdout
