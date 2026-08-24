# Foreshadow P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a local Python CLI that, once per UTC day, discovers emerging public GitHub repos, scores them explainably, writes at most five cards (empty is success), and records a human review — never writing to third-party GitHub.

**Architecture:** Batch CLI (`foreshadow run`) over SQLite. GraphQL-first GET-only GitHub client. Daily snapshots **are** star history. Pure functions for features / H-rules / score / select so default tests never open a socket. Top 5 requires a defined 7-day star velocity (`v7`).

**Tech Stack:** Python 3.12+, uv, hatchling, httpx, pydantic v2, typer, platformdirs, sqlite3, pytest, ruff, respx.

**Spec:** [`docs/p0-architecture.md`](../../p0-architecture.md) (Accepted, 2026-08-24). If this plan and the spec disagree, **the spec wins** — then patch the plan.

## Global Constraints

- Language: Python 3.12 only in P0. `requires-python = ">=3.12"`. CI 3.12 and 3.13. **No Go. No dual-language stack.**
- CLI name `foreshadow`; import `foreshadow`; PyPI `foreshadow-radar`.
- Runtime deps only: `httpx`, `pydantic>=2`, `typer`, `platformdirs`. Stdlib: `sqlite3`, `tomllib`.
- Forbidden: PyGithub, pandas, numpy, SQLAlchemy, asyncio, TUI, official LLM SDKs, GitHub write APIs, stargazer listing, GraphQL `watchers`, `/traffic/*`, `/stats/*`.
- Token: `GITHUB_TOKEN` → `GH_TOKEN` → `gh auth token`. Never in TOML, SQLite, logs, fixtures.
- Opportunity weights (points, must sum to 100): 20 / 15 / 15 / 20 / 15 / 10 / 5. Exit 2 if not.
- Top 5 iff Opportunity ≥ 55 AND Explosion ≥ 35 AND `v7` defined. Lifetime `stars/age` is **not** Explosion.
- Max 5 cards. Empty Top 5 is success (exit 0). Never pad.
- Missing windows / Phase-B-missing fields are `NA` (`None`), not `0`. NA mix: drop the term, do not renormalize.
- REST `open_issues_count` includes PRs — never store it as `open_issues`. REST `watchers_count` aliases stars — `snapshots.watchers` stays NULL.
- Identity: GraphQL `node_id`. `full_name` is mutable.
- UTC calendar dates. License MIT. No telemetry. DB file mode 0600.
- Default tests never talk to `api.github.com`.
- Intended remote: `rainhuang0220/foreshadow`.
- Formula bodies: copy from spec **Scoring formulas**, **H1–H10**, **Phase-B-missing → NA**, **Selection**. Do not invent a second scoring system.

## File map

| Path | Responsibility |
|---|---|
| `pyproject.toml` / `uv.lock` | Package `foreshadow-radar`, script `foreshadow`, hatchling package-data |
| `src/foreshadow/cli.py` | Typer app: `run`, `report`, `show`, `review`, `watchlist` |
| `src/foreshadow/config.py` | TOML load order, weight sum, defaults |
| `src/foreshadow/paths.py` | `FORESHADOW_HOME` / platformdirs |
| `src/foreshadow/clock.py` | Injectable UTC clock |
| `src/foreshadow/db.py` | Connect, pragmas, migrate via `importlib.resources` |
| `src/foreshadow/sql/001_init.sql` | Schema v1 (verbatim from spec) |
| `src/foreshadow/models.py` | `ComponentScore`, `ScoreBreakdown`, `FeaturesBlob`, `ReportJSON` |
| `src/foreshadow/directions.toml` | Direction bags |
| `src/foreshadow/github/client.py` | GET-only + GraphQL query, budget, backoff, `resolve_token` |
| `src/foreshadow/github/queries.py` | GraphQL documents from spec |
| `src/foreshadow/github/cache.py` | Same-day GraphQL cache; `--force` bypass |
| `src/foreshadow/github/rest.py` | Contributors, commits, contents, workflows, community |
| `src/foreshadow/pipeline/features.py` | Windows, NA, README/tree/issue features |
| `src/foreshadow/pipeline/h_rules.py` | H1–H10 / P1–P8 |
| `src/foreshadow/pipeline/direction.py` | Keyword/topic/language fit |
| `src/foreshadow/pipeline/score.py` | Seven components + Explosion + mix |
| `src/foreshadow/pipeline/select.py` | Thresholds, v7 gate, diversity skip-and-continue |
| `src/foreshadow/pipeline/discover.py` | 12 templated searches, cap 120 |
| `src/foreshadow/pipeline/hydrate.py` | Phase A/B, identity, collisions |
| `src/foreshadow/pipeline/snapshot.py` | Upsert daily snapshot |
| `src/foreshadow/pipeline/report.py` | Markdown + `ReportJSON` |
| `src/foreshadow/pipeline/__init__.py` | `run_pipeline` |
| `src/foreshadow/reviews.py` | Append-only reviews + Enter |
| `src/foreshadow/llm.py` | Optional narrative after select |
| `tests/` | One module per concern; fixtures under `tests/fixtures/` |

---

### Task 1: Repo skeleton

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `LICENSE`, `README.md`, `README.zh-CN.md`, `CONTRIBUTING.md`, `.github/workflows/ci.yml`, `.github/ISSUE_TEMPLATE/bug.yml`, `.github/PULL_REQUEST_TEMPLATE.md`, `src/foreshadow/__init__.py`, `src/foreshadow/__main__.py`, `src/foreshadow/cli.py`, `tests/test_cli_help.py`
- Modify: `CHANGELOG.md`, `PROJECT_STATE.md`, `TODO.md` (already exist — keep honest)

**Interfaces:**
- Consumes: nothing
- Produces: package import `foreshadow`, `__version__ = "0.0.0"`, Typer app `foreshadow.cli:app` with `--help`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_help.py
from typer.testing import CliRunner
from foreshadow.cli import app

def test_help_lists_commands():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("run", "report", "show", "review", "watchlist"):
        assert name in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -c "import foreshadow"  # expect ModuleNotFoundError
```

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:

```toml
[project]
name = "foreshadow-radar"
version = "0.0.0"
description = "Find what the future has already foreshadowed."
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.12"
authors = [{ name = "rainhuang0220" }]
dependencies = [
  "httpx",
  "pydantic>=2",
  "typer",
  "platformdirs",
]

[project.scripts]
foreshadow = "foreshadow.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/foreshadow"]

[tool.hatch.build.targets.wheel.force-include]
"src/foreshadow/sql" = "foreshadow/sql"
"src/foreshadow/directions.toml" = "foreshadow/directions.toml"

[dependency-groups]
dev = ["pytest", "ruff", "respx"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
target-version = "py312"
src = ["src", "tests"]
```

`.python-version` contents: `3.12`

`src/foreshadow/__init__.py`: `__version__ = "0.0.0"`

`src/foreshadow/__main__.py`:

```python
from foreshadow.cli import app
if __name__ == "__main__":
    app()
```

`src/foreshadow/cli.py`:

```python
import typer
app = typer.Typer(no_args_is_help=True, add_completion=False)

@app.command()
def run(force: bool = False, date: str | None = None, llm: bool = False) -> None:
    raise NotImplementedError

@app.command()
def report(date: str | None = None, json: bool = False) -> None:
    raise NotImplementedError

@app.command()
def show(repo: str) -> None:
    raise NotImplementedError

@app.command()
def review(repo: str, action: str, m: str | None = None) -> None:
    raise NotImplementedError

@app.command()
def watchlist(action: str | None = None) -> None:
    raise NotImplementedError
```

README.md **must** contain these sentences verbatim:

- Empty Top 5 is OK.
- Top 5 requires ~7 daily snapshots (`v7`); day 1 is empty by construction.
- Lifetime `stars/age` is not Explosion.
- Token stays on the machine.
- We only GET public GitHub.
- This is not trending.

LICENSE: MIT, `Copyright (c) 2026 rainhuang0220`.

`.gitignore`: `.env`, `.venv`, `dist/`, `data/`, `reports/`, `*.sqlite3`, `__pycache__/`, `.ruff_cache/`.

CI (`.github/workflows/ci.yml`): ruff + pytest on 3.12 and 3.13; `contents: read`; pin action SHAs; no network to `api.github.com`.

- [ ] **Step 4: Run test to verify it passes**

```bash
uv sync --group dev
uv run ruff check src tests
uv run pytest tests/test_cli_help.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit** (if git is initialized; otherwise `git init` first)

```bash
git add pyproject.toml src tests README.md README.zh-CN.md LICENSE CONTRIBUTING.md .github .python-version .gitignore
git commit -m "chore: P0 skeleton (MIT, uv, ruff, CI, README)"
```

---

### Task 2: Config, paths, clock, models, SQLite v1

**Files:**
- Create: `src/foreshadow/config.py`, `paths.py`, `clock.py`, `models.py`, `db.py`, `src/foreshadow/sql/001_init.sql`, `src/foreshadow/directions.toml`, `examples/config.toml`, `tests/conftest.py`, `tests/test_db.py`, `tests/test_config.py`
- Modify: `pyproject.toml` (package-data already in Task 1)

**Interfaces:**
- Consumes: package layout from Task 1
- Produces:
  - `load_config(cwd: Path | None = None) -> Settings`
  - `Settings` pydantic model with `discovery`, `scoring`, `github`, `llm` nested models matching spec TOML keys
  - `resolve_data_dir() -> Path` (`FORESHADOW_HOME` else platformdirs `user_data_dir("foreshadow")`)
  - `Clock` with `now() -> datetime` (UTC) and `today() -> date`
  - `connect(path: Path) -> sqlite3.Connection` (mode 0600, WAL, `foreign_keys=ON`, `busy_timeout=5000`)
  - `migrate(conn) -> None` applying `sql/001_init.sql` via `importlib.resources.files("foreshadow").joinpath("sql/001_init.sql")`
  - `ComponentScore`, `ScoreBreakdown`, `FeaturesBlob`, `ReportJSON` in `models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/conftest.py
import os
from pathlib import Path
import pytest
from foreshadow.clock import Clock
from datetime import datetime, timezone, date

@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("FORESHADOW_HOME", str(home))
    return home

@pytest.fixture
def frozen_clock():
    return Clock(now=datetime(2026, 8, 24, 0, 5, tzinfo=timezone.utc))
```

```python
# tests/test_config.py
import pytest
from foreshadow.config import load_config, Settings

def test_default_weights_sum_to_100():
    s = load_config()
    w = s.scoring
    assert w.momentum_weight + w.real_user_weight + w.gap_weight + w.contribution_opp_weight + w.early_entry_weight + w.direction_fit_weight + w.maintainer_weight == 100

def test_fractional_weights_exit_2(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[scoring]\nmomentum_weight = 0.20\nreal_user_weight = 15\ngap_weight = 15\ncontribution_opp_weight = 20\nearly_entry_weight = 15\ndirection_fit_weight = 10\nmaintainer_weight = 5\n")
    monkeypatch.setenv("FORESHADOW_CONFIG", str(cfg))
    with pytest.raises(SystemExit) as ei:
        load_config()
    assert ei.value.code == 2

def test_does_not_overwrite_existing_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[discovery]\nstar_min = 99\n")
    monkeypatch.setenv("FORESHADOW_CONFIG", str(cfg))
    # first-run helper must not overwrite
    from foreshadow.config import ensure_default_config
    ensure_default_config(cfg)
    assert "star_min = 99" in cfg.read_text()
```

```python
# tests/test_db.py
from foreshadow.db import connect, migrate

def test_schema_unique_snapshot(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    conn.execute("INSERT INTO repos(node_id, full_name, owner, name, first_seen_at, last_seen_at) VALUES ('X','a/b','a','b','t','t')")
    rid = conn.execute("SELECT id FROM repos").fetchone()[0]
    conn.execute("INSERT INTO snapshots(repo_id, snapshot_date, captured_at, completeness) VALUES (?,?,?,1)", (rid, "2026-08-24", "t"))
    import sqlite3
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO snapshots(repo_id, snapshot_date, captured_at, completeness) VALUES (?,?,?,1)", (rid, "2026-08-24", "t"))

def test_sql_packaged():
    import importlib.resources
    text = importlib.resources.files("foreshadow").joinpath("sql/001_init.sql").read_text()
    assert "CREATE TABLE repos" in text
    assert "unique_human_authors_100" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py tests/test_db.py -v
```

Expected: FAIL (modules missing).

- [ ] **Step 3: Write minimal implementation**

1. Paste the **entire** `CREATE TABLE` block from `docs/p0-architecture.md` section **CREATE TABLE SQL** into `src/foreshadow/sql/001_init.sql` (schema_migrations through raw_payloads). Do not add `unique_human_authors_100` or `top_author_share_100`.
2. `Settings` fields **must** match spec TOML keys: `star_min`, `star_max`, `pushed_within_days`, `max_candidates=120`, `max_deep_hydrate=30`, `max_watchlist_deep=20`, `per_page=25`, `exclude_forks=true`, `exclude_archived=true`, `languages`, scoring weights, `min_opportunity=55`, `min_explosion=35`, `reject_cooldown_days=90`, `later_skip_days=14`, `max_per_owner=2`, `window_slack_days=1`, github budgets 800/400, `llm.enabled=false`.
3. Load order: code defaults → `$FORESHADOW_CONFIG` or `~/.config/foreshadow/config.toml` → `./foreshadow.toml` (later wins). Token is never a config field.
4. `models.py`:

```python
from typing import Literal
from pydantic import BaseModel, Field

class ComponentScore(BaseModel):
    value: float | None = None
    confidence: Literal["low", "medium", "high"]
    missing: list[str] = Field(default_factory=list)
    weight: float | None = None
    why: str = ""

class ScoreBreakdown(BaseModel):
    opportunity: ComponentScore
    explosion: ComponentScore
    contribution: ComponentScore
    momentum: ComponentScore
    real_user: ComponentScore
    gap: ComponentScore
    contribution_opp: ComponentScore
    early_entry: ComponentScore
    direction_fit: ComponentScore
    maintainer: ComponentScore
    flags: list[str] = Field(default_factory=list)
    vetoed: bool = False
    veto_reason: str | None = None
    exceptional: str | None = None
    selected_rank: int | None = None

class FeaturesBlob(BaseModel):
    """Deep hydrate. Missing Phase-B fields stay None, never 0-filled."""
    readme_excerpt: str | None = None
    readme_install: int | None = None
    screenshot_only: bool | None = None
    root_names: list[str] | None = None
    has_workflows: bool | None = None
    community_health: float | None = None
    contributing: bool | None = None
    U_issue: int | None = None
    U_issue_ext: int | None = None
    bug_n: int | None = None
    talk_n: int | None = None
    usage_closed_n: int | None = None
    help_n: int | None = None
    repeat_clusters: int | None = None
    maint_touch: float | None = None
    I_open: int | None = None
    I_closed: int | None = None
    P_open: int | None = None
    sample_open_n: int | None = None
    topics: list[str] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)

class ReportJSON(BaseModel):
    date: str
    reason: str | None = None
    snapshot_days: int
    cards: list[dict]
    active: list[dict]
    watchlist_appendix: list[dict]
    below_bar: list[dict]
    rejected_counts: dict
    source_health: dict
```

`directions.toml`: one table per spec direction bag (LLM, Agent, MCP, RAG/memory, world-model, eval/tooling, AI infra, Rust/systems, RISC-V, compiler/OS) with `topics`, `keywords`, `languages` lists from spec § Direction Fit.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py tests/test_db.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/foreshadow tests/conftest.py tests/test_db.py tests/test_config.py examples/config.toml
git commit -m "feat: config TOML, platformdirs, SQLite schema v1"
```

---

### Task 3: Features, windows, NA

**Files:**
- Create: `src/foreshadow/pipeline/__init__.py`, `src/foreshadow/pipeline/features.py`, `tests/test_features.py`
- Test: `tests/test_features.py`

**Interfaces:**
- Consumes: `Clock`, `FeaturesBlob`, `window_slack_days`
- Produces:
  - `clip01(x: float) -> float`
  - `star_velocity(snapshots: list[SnapshotPoint], today, n: int, slack_days: int) -> tuple[float | None, str | None]`
    returns `(value, source)` where source is `"exact"` | `"nearest-1d"` | `None`
  - `compute_windows(...)` → `v7`, `v30`, `v90`, `rel_growth_7d`, `accel_ratio`, `lifetime_star_rate`, `v7_source`
  - `readme_install(text: str) -> int`
  - `screenshot_only(text: str) -> bool`
  - `is_readme_only_tree(names: list[str]) -> bool`  # H3 tree heuristic
  - `SnapshotPoint(date, stars, forks, pushed_at)` dataclass

Lookup rule: use the latest snapshot with `date <= t-N` and `t-N - date <= slack_days`. Else NA. **Do not impute 0.** Test: snapshots on t, t-6, t-8 → v7 uses t-8 (`nearest-1d`). Snapshots on t and t-9 only → v7 NA.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_features.py
from datetime import date
from foreshadow.pipeline.features import (
    clip01, star_velocity, SnapshotPoint, readme_install, screenshot_only, is_readme_only_tree,
)

def test_clip01():
    assert clip01(-1) == 0
    assert clip01(0.5) == 0.5
    assert clip01(2) == 1

def test_v7_nearest_slack():
    t = date(2026, 8, 24)
    snaps = [
        SnapshotPoint(date(2026, 8, 24), 900, 85, None),
        SnapshotPoint(date(2026, 8, 18), 400, 40, None),  # t-6
        SnapshotPoint(date(2026, 8, 16), 200, 18, None),  # t-8
    ]
    v, src = star_velocity(snaps, t, 7, slack_days=1)
    assert src == "nearest-1d"
    assert abs(v - (900 - 200) / 7) < 1e-6

def test_v7_too_old_is_na():
    t = date(2026, 8, 24)
    snaps = [
        SnapshotPoint(date(2026, 8, 24), 900, 85, None),
        SnapshotPoint(date(2026, 8, 15), 200, 18, None),  # t-9
    ]
    v, src = star_velocity(snaps, t, 7, slack_days=1)
    assert v is None and src is None

def test_install_verb():
    assert readme_install("# x\n\npip install memkit\n") == 1
    assert readme_install("# pretty\n![a](a.gif)\n![b](b.gif)\n") == 0

def test_gemfile_only_is_not_h3():
    assert is_readme_only_tree(["README.md", "Gemfile"]) is False
    assert is_readme_only_tree(["README.md", "LICENSE", ".gitignore"]) is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_features.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation** in `features.py` matching spec **Feature computation**, **README install**, **Tree heuristic (H3)**. Velocity denominator is still `N` (7/30/90), not the actual gap. Record `v7_source`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_features.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/foreshadow/pipeline/features.py tests/test_features.py
git commit -m "feat: snapshot windows, NA velocity, README/tree features"
```

---

### Task 4: H-rules and direction bags

**Files:**
- Create: `src/foreshadow/pipeline/h_rules.py`, `src/foreshadow/pipeline/direction.py`, `tests/test_h_rules.py`, `tests/test_direction.py`
- Modify: `src/foreshadow/directions.toml` if Task 2 stub is incomplete

**Interfaces:**
- Consumes: `FeaturesBlob`, repo scalars (S, C, age_days, …)
- Produces:
  - `h7_fold(s: str) -> str`
  - `evaluate_h(repo) -> HResult(fired: list[str], vetoed: bool, veto_reason: str | None)`
    `veto_reason` = comma-joined fired IDs in H1…H10 order
  - `apply_penalties(scores, repo) -> scores` for P1–P8
  - `score_direction(name, description, topics, headings, language, bags) -> int`  # 0–100

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_h_rules.py
from foreshadow.pipeline.h_rules import h7_fold, evaluate_h

class R:
    def __init__(self, **kw):
        self.__dict__.update(dict(
            archived=False, disabled=False, is_empty=False, is_fork=False,
            S=0, C=1, C_censored=False, age_days=12, has_issues=True,
            I_open=0, I_closed=0, fork_star=0.0014, U_commit_30d=1,
            license_spdx=None, pushed_age_days=10, readme_install=0,
            name="chatgpt-wrapper-pro", full_name="quick/chatgpt-wrapper-pro",
            description="", topics=[], readme_excerpt="Best ChatGPT wrapper GPT-4 AI Agent 🔥",
            root_names=["README.md", "app.py"],
        ), **kw)

def test_h7_fold_needles_and_haystack():
    assert h7_fold("GPT-4 wrapper") == "gpt 4 wrapper"
    assert h7_fold("gpt-4 wrapper") == "gpt 4 wrapper"
    assert h7_fold("gpt-4 wrapper") in h7_fold("Best GPT-4 wrapper")

def test_12c_fires_h5_h6_h7():
    r = evaluate_h(R(S=8400, C=1, age_days=12, fork_star=0.0014, U_commit_30d=1, I_open=0, has_issues=True))
    assert r.veto_reason == "H5,H6,H7"

def test_name_only_chatgpt_wrapper_fires_h7():
    r = evaluate_h(R(S=100, C=1, age_days=20, readme_excerpt="", I_open=5, fork_star=0.1, U_commit_30d=1))
    assert "H7" in r.fired

def test_gpt4_wrapper_readme_fires_h7():
    r = evaluate_h(R(name="x", full_name="a/x", S=100, C=1, age_days=20,
                     readme_excerpt="GPT-4 wrapper", readme_install=0, I_open=5, fork_star=0.1))
    assert "H7" in r.fired

def test_gemfile_not_h3():
    r = evaluate_h(R(S=10, C=3, age_days=40, root_names=["README.md", "Gemfile"],
                     readme_excerpt="ok", I_open=1, fork_star=0.1, U_commit_30d=2, license_spdx="MIT"))
    assert "H3" not in r.fired
```

`test_direction.py`: bag hit on topics `memory,rag,llm` returns ≥70; stuffing ≥4 of `{ai,llm,agent,gpt,rag,awesome,best,ultimate}` is detected for P7 (penalty applied in score.py, detection can live here).

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_h_rules.py tests/test_direction.py -v
```

- [ ] **Step 3: Implement** H1–H10 exactly as spec table. H7:

```python
SPAM_LEXICON = [
    "chatgpt wrapper", "gpt-4 wrapper", "gpt4o wrapper", "best ai agent",
    "auto gpt", "airdrop", "free crypto", "1000 stars", "buy followers",
    "openai api key", "jailbreak gpt", "trending",
]

def h7_fold(s: str) -> str:
    s = (s or "").lower().replace("-", " ").replace("_", " ")
    return " ".join(s.split())
```

Haystack = name + full_name + description + topics + README excerpt, folded. Needle folded the same way. H2 always fires on forks. H9 treats `NOASSERTION` as unlicensed. P8: when `S(t-1)` exists, `Δ1d ≥ 50` and `U_commit_30d == 0` → penalty (not a silent Top 5). P5 = `clip(Gap - 10, 0, 100)` in score.py.

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: H1–H10/P1–P8 and direction bags"
```

---

### Task 5: Score, select, worked examples (merge blocker)

**Files:**
- Create: `src/foreshadow/pipeline/score.py`, `src/foreshadow/pipeline/select.py`, `tests/test_score.py`, `tests/test_select.py`, `tests/test_worked_examples.py`, `tests/test_cold_start.py`, `tests/test_exceptional.py`, `tests/fixtures/repos/memkit.json`, `giant.json`, `wrapper.json`

**Interfaces:**
- Consumes: `Settings.scoring` weights, `HResult`, feature values, `ComponentScore`
- Produces:
  - `mix_opportunity(components: dict[str, ComponentScore], weights) -> ComponentScore`  # drop NA terms, no renormalize
  - `score_repo(...) -> ScoreBreakdown`
  - `select_top(rows: list[ScoreBreakdown], *, min_opportunity=55, min_explosion=35, max_per_owner=2) -> list[ScoreBreakdown]`
    Requires `v7` defined (`momentum.confidence` in `{medium,high}` **and** `momentum.value is not None`) **and** `explosion.value is not None` **and** Opportunity ≥ 55 **and** Explosion ≥ 35. Diversity: while walking sorted pool, skip if owner already has 2; continue until 5 or pool exhausted. Never pad.

**12.A locked numbers** (tolerance ±0.5 except DirectionFit fixture = 92):

| Field | Value |
|---|---|
| Momentum | 95.2 |
| RealUser | 97.5 |
| Gap | 88.9 |
| ContributionOpp / Contribution | 61.9 |
| EarlyEntry | 84.0 |
| DirectionFit | **92** (fixture input, not bag output) |
| MaintainerQuality | **77.55** |
| Opportunity | **85.05** |
| Explosion | 93.6 |

12.A inputs: S(t)=900, S(t-7)=200, S(t-30)=180, F=85, C=8, age=75, U_commit_30d=5, I_open=34, U_issue=28, U_issue_ext=22, bug_n=12, talk_n=20, usage_closed_n=5, help_n=4, repeat_clusters=1, license MIT, CI yes, tests yes, CONTRIBUTING no, pip install, topics memory/rag/llm, pushed 1d, maint_touch=0.45, health=71.

12.B: C_censored, S=100000, v7=v30=50/day → Opportunity < 55, Explosion < 35, Gap == 10. Do **not** assert ≈35.8 ±0.5.

12.C: `veto_reason == "H5,H6,H7"`, `explosion.value is None`, not selected.

Cold start: 12.A fields with only today’s snapshot → `selected_rank is None`, `explosion.value is None`, `explosion_lifetime_proxy` may exist. Same repo with t-7 present → keep.

- [ ] **Step 1: Write the failing tests** — `tests/test_worked_examples.py` asserts the table above; `test_cold_start.py` (a)/(b); `test_select.py`:

```python
from foreshadow.models import ComponentScore, ScoreBreakdown
from foreshadow.pipeline.select import select_top

def passing(owner: str, name: str, opp: float) -> ScoreBreakdown:
    hi = ComponentScore(value=80, confidence="high")
    row = ScoreBreakdown(
        opportunity=ComponentScore(value=opp, confidence="high"),
        explosion=ComponentScore(value=80, confidence="high"),
        contribution=hi, momentum=ComponentScore(value=90, confidence="high"),
        real_user=hi, gap=hi, contribution_opp=hi, early_entry=hi,
        direction_fit=hi, maintainer=hi,
    )
    row.full_name = f"{owner}/{name}"  # select_top reads this attribute
    row.owner = owner
    return row

def test_diversity_skip_and_continue():
    rows = [
        passing("a", "r1", 90), passing("a", "r2", 89), passing("a", "r3", 88),
        passing("b", "x", 87), passing("c", "y", 86), passing("d", "z", 85),
    ]
    top = select_top(rows, min_opportunity=55, min_explosion=35, max_per_owner=2)
    names = [r.full_name for r in top]
    assert names == ["a/r1", "a/r2", "b/x", "c/y", "d/z"]

def test_no_pad():
    top = select_top([passing("a", "r1", 90), passing("b", "r2", 80)])
    assert len(top) == 2

def test_v7_required():
    row = passing("a", "r1", 90)
    row.momentum.value = None
    row.momentum.confidence = "low"
    row.explosion.value = None
    assert select_top([row]) == []
```

`test_score.py`: NA mix (Momentum None → Opportunity omits 20 points); Phase-A-only → real_user/contribution_opp/gap/early_entry None if C missing; confidence **low first**.

`test_exceptional.py`: day-31+ snapshots only. DirectionFit=40, Five≥85, min≥75 → `exceptional_override_weak_fit`. DirectionFit=30 + H7 crypto → not eligible.

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest tests/test_worked_examples.py tests/test_cold_start.py tests/test_select.py tests/test_score.py tests/test_exceptional.py -v
```

- [ ] **Step 3: Implement `score.py` and `select.py`** using spec **Scoring formulas** and **Selection** verbatim (clip01, NA mix, Explosion NULL when v7 NA, lifetime proxy in evidence only). `health=0.71`, `fresh=1`, `response=0.45`, `license_ok=1` → Maintainer = `100*(0.30*0.71 + 0.30*1 + 0.25*0.45 + 0.15*1) = 77.55`.

- [ ] **Step 4: Run tests — expect PASS** (merge blocker)

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: Opportunity/Explosion/Contribution scores and Top 5 select"
```

---

### Task 6: GET-only GitHub client

**Files:**
- Create: `src/foreshadow/github/__init__.py`, `client.py`, `queries.py`, `cache.py`, `rest.py`, `tests/test_client_get_only.py`, `tests/test_github_errors.py`, `tests/fixtures/graphql/hydrate_a.json`, `tests/fixtures/rest/contributors.json`

**Interfaces:**
- Consumes: `Settings.github`, token env
- Produces:
  - `resolve_token() -> str`  # env order; SystemExit 2 if missing
  - `class WriteAttemptError(RuntimeError): ...`
  - `class GitHubClient:`
    - `request(method, url, **kw)` — GET/HEAD only for REST
    - `graphql(document: str, variables: dict, *, force: bool = False) -> dict`
    - `get(path: str, params: dict | None = None) -> httpx.Response`
  - Documents in `queries.py`: `SEARCH_REPOS`, `HYDRATE_A`, `HYDRATE_A_NODE`, `HYDRATE_B`, `HYDRATE_B_NODE`, `HYDRATE_B_STRIPPED` — **copy the GraphQL from spec Hydrate / Discovery**. Every connection has `first:`. **No `watchers` field.**

Denylist exact path templates: `/repos/{owner}/{repo}/stargazers` (allow `/stargazers/count` if used), `/subscribers`, `/traffic/*`, `/stats/*`, `/network/dependents`. GraphQL: after stripping comments, first operation token must not be `mutation`. A query containing the English word “mutation” in a string must pass.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_client_get_only.py
import pytest
from foreshadow.github.client import GitHubClient, WriteAttemptError

def test_rest_post_raises_before_socket():
    c = GitHubClient(token="x", transport=None)  # no real transport
    with pytest.raises(WriteAttemptError):
        c.request("POST", "https://api.github.com/repos/a/b/issues", json={})

def test_mutation_document_rejected():
    c = GitHubClient(token="x")
    with pytest.raises(WriteAttemptError):
        c.graphql("mutation { addStar(input:{starrableId:\\"x\\"}) { clientMutationId } }", {})

def test_word_mutation_in_description_allowed(respx_mock):
    import httpx
    respx_mock.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(200, json={"data": {"search": {"repositoryCount": 0}}})
    )
    c = GitHubClient(token="x")
    doc = 'query Q { search(query: "mutation", type: REPOSITORY, first: 1) { repositoryCount } }'
    c.graphql(doc, {})  # must not raise WriteAttemptError

def test_stargazers_list_denied_count_allowed():
    c = GitHubClient(token="x")
    with pytest.raises(WriteAttemptError):
        c.get("/repos/a/b/stargazers")
```

`test_github_errors.py` with respx: 404, 429 (retry then source_failure), 502 → retry `HYDRATE_B_STRIPPED`.

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement client** sequential HTTP, `search_spacing_ms`, GraphQL cost from `rateLimit.cost` / headers, stop when remaining < 80, `--force` skips same-day cache, REST ETag 304 kept. Optional GraphQL `errors[]` on unused fields do **not** mark incomplete.

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: GET-only GraphQL/REST client with budget and backoff"
```

---

### Task 7: Discover, hydrate, snapshot

**Files:**
- Create: `src/foreshadow/pipeline/discover.py`, `hydrate.py`, `snapshot.py`, `tests/test_discover_merge.py`, `test_rename.py`, `test_pre_rank.py`, `test_budget_caps.py`, `test_hydrate.py`, `test_idempotency.py`
- A `FakeGitHub` in `tests/fakes.py` returning fixtures by `node_id`, with `hydrate_calls: int = 0` incremented on every hydrate (for `test_show_does_not_hydrate_unknown`)

**Interfaces:**
- Consumes: `GitHubClient`, `Settings.discovery`, `run_id`
- Produces:
  - `search_candidates(client, settings, today) -> list[SearchHit]`  # 12 templated queries, `{star_min}`, `{star_max}`, `{pushed45}`; **no `fork:false`**; `sort:stars` in the breakout query string only
  - `cap_candidates(watchlist_ids, search_hits, max_candidates=120) -> CapResult`  # watchlist newest first truncated, then search fill; flags `watchlist_truncated`, `search_capped`
  - `identity_ids(capped, conn) -> set[str]`  # known node_ids in the 120 ∪ active rows whose full_name matches those 120
  - `pre_rank_key(repo) -> tuple`  # spec: direction hit desc, in_star_band, recency bucket, stargazerCount
  - `phase_b_shortlist(candidates, watchlist_actions, max_deep=30, max_watchlist_deep=20) -> list`
    Reservation = latest action ∈ `{watch, interested, investigate}` (later after skip expiry). **`enter` is Phase A only.** Invariants: `|phase_b| == min(30, |rankable|)` and `enter ∩ phase_b == ∅` and `|phase_b ∩ W_rankable| >= min(20, |W_rankable|)`.
  - `upsert_snapshot(conn, repo_id, date, payload) -> None`
  - `apply_identity(conn, client, identity_ids, search_hits)` — `HydrateANode` first; on 404 suffix `full_name` with `#deleted-{node_id}` **then** insert new occupant in **one transaction**. Never `UPDATE full_name` onto another active row.

Map GraphQL `issues(states:OPEN).totalCount` → `snapshots.open_issues`. Never REST `open_issues_count`. Never store `watchers_count`. `snapshots.watchers` NULL.

- [ ] **Step 1: Write the failing tests**

`test_budget_caps.py`:
- 400 historical repos + 12 search hits, empty watchlist → Phase A calls ≤ 12 + |collisions|
- 150 watchlist + 200 search → 120 candidates, `watchlist_truncated=true`, extra 30 watchlist **not** hydrated
- 20 enter + 10 rankable → enter ∉ phase_b
- `search_capped` is **not** degraded

`test_rename.py`: same run sees old node 404 and new node with the old `full_name` → suffix then insert.

`test_hydrate.py`: REST payload with `open_issues_count` / `watchers_count` does not land in `snapshots.open_issues` / `snapshots.watchers`.

`test_pre_rank.py`: three fixtures always pick the same 30.

`test_idempotency.py`: second `run` same UTC date replaces candidates/scores, does not duplicate reviews.

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement** pipeline order: search → cap 120 → identity on that 120 ∪ collisions → Phase A remainder → Phase B → snapshot. Phase A ≤ 120 + |collisions|. Contributor pagination **stops early** (short page, or 500 identified, or C≥80). Unique committers 30d = unique authors, never commit count.

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: discovery, two-phase hydrate, daily snapshots"
```

---

### Task 8: Report + `run` / `report` / `show`

**Files:**
- Create: `src/foreshadow/pipeline/report.py`, `tests/test_report.py`, `examples/report-sample.md`, `examples/report-sample-empty.md`
- Modify: `src/foreshadow/cli.py`, `src/foreshadow/pipeline/__init__.py`

**Interfaces:**
- Consumes: `ScoreBreakdown`, `ReportJSON`, `run_pipeline` pieces from Tasks 5–7
- Produces:
  - `render_markdown(report: ReportJSON) -> str`
  - `render_json(report: ReportJSON) -> str`
  - `run_pipeline(*, clock: Clock, force: bool, llm: bool) -> RunResult(status, report_path, top5_count)`
  - CLI `run` / `report` / `show` wired

Card format: spec **Report markdown format** (Opportunity / Explosion / Contribution, Why now, five-point analysis, Direction Fit, best contribution, Risk, confidence). Header prints snapshot-history depth, e.g. `Explosion caveat: 3 snapshot-days of history (v7 undefined; Top 5 empty)`.

`degraded` iff `search_truncated OR budget_abort OR hydrate_failed > 0 OR watchlist_truncated`. `complete` includes Top 5 = 0. `--force` only if today’s status is `complete`; `running`/`failed`/`degraded` re-run without the flag. `show` unknown name → exit 2, **do not hydrate**.

Stdout:

```
Foreshadow 2026-08-24
discovered 96  hydrated 88  scored 88  selected 3  (degraded: search truncated)
snapshots: 4 days of history  (Explosion still weak until ~7)
report: .../reports/2026-08-24.md
review: foreshadow review owner/repo interested
```

Exit 0 on empty Top 5 and on degraded.

- [ ] **Step 1: Write failing tests** in `test_report.py` (golden empty + 12.A card JSON keys from spec ReportJSON; header contains `v7`; at most 5 cards; no forbidden prophecy phrases “will explode” / “next LangChain”).

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement renderer + `run_pipeline` + CLI**

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/test_report.py tests/test_cli_help.py tests/test_idempotency.py -v
```

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: daily markdown Top 5 report and run CLI"
```

---

### Task 9: Review, Enter, watchlist

**Files:**
- Create: `src/foreshadow/reviews.py`, `tests/test_review.py`, `tests/test_watchlist.py`
- Modify: `src/foreshadow/cli.py`

**Interfaces:**
- Consumes: `GitHubClient`, `score_repo`, hydrate Phase B
- Produces:
  - `ACTIONS = ("watch", "interested", "reject", "investigate", "enter", "later")`
  - `apply_review(conn, client, repo_ref: str, action: str, note: str | None, clock) -> None`
    Resolve `full_name` then aliases then GraphQL. Unseen: **Phase B** hydrate one node, then `score_repo`, then insert review. `enter` upserts `entries` with `stars_at_entry`, `contributors_at_entry`, `scores_at_entry_json` (never invented `{}`).
  - `current_stances(conn, action: str | None) -> list`
  - Reject cooldown 90d / later skip 14d filter Top 5 eligibility (not ranking nudges).

- [ ] **Step 1: Write failing tests**

```python
from foreshadow.reviews import apply_review, current_stances
from foreshadow.db import connect, migrate
from foreshadow.pipeline import run_pipeline
from typer.testing import CliRunner
from foreshadow.cli import app

def test_enter_writes_entry_and_scores(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    apply_review(conn, fake_github, "acme/memkit", "enter", "docs", frozen_clock)
    row = conn.execute("SELECT stars_at_entry, scores_at_entry_json FROM entries").fetchone()
    assert row[0] is not None
    assert row[1] != "{}"

def test_rerun_does_not_duplicate_reviews(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    apply_review(conn, fake_github, "acme/memkit", "watch", None, frozen_clock)
    run_pipeline(clock=frozen_clock, force=True, llm=False)
    n = conn.execute("SELECT count(*) FROM reviews").fetchone()[0]
    assert n == 1

def test_show_does_not_hydrate_unknown(tmp_home, fake_github):
    result = CliRunner().invoke(app, ["show", "nope/unknown"])
    assert result.exit_code == 2
    assert fake_github.hydrate_calls == 0

def test_watchlist_lists_all_without_flag(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    apply_review(conn, fake_github, "acme/memkit", "watch", None, frozen_clock)
    apply_review(conn, fake_github, "acme/other", "enter", None, frozen_clock)
    rows = current_stances(conn, action=None)
    assert {r["action"] for r in rows} >= {"watch", "enter"}
```

- [ ] **Step 2: FAIL → Step 3: implement → Step 4: PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: human review actions and entry snapshots"
```

This task is **required for 0.1.0**.

---

### Task 10: Optional LLM narrative (not required for 0.1.0)

**Files:**
- Create: `src/foreshadow/llm.py`, `tests/test_llm_does_not_score.py`
- Modify: `src/foreshadow/pipeline/__init__.py` (call **after** `select_top`)

**Interfaces:**
- Consumes: selected `ScoreBreakdown` cards only
- Produces: `fill_why_now(cards, settings) -> list[str]` — one OpenAI-compatible `POST {base_url}/chat/completions` per selected card (≤5). Env key only (never in TOML). On any failure, keep rule-based why-now. **Must not mutate scores, vetoes, or rank.**

- [ ] **Step 1: Failing test**

```python
def test_llm_raise_leaves_scores_identical(monkeypatch):
    before = score_repo(memkit)
    selected = select_top([before])
    monkeypatch.setattr("foreshadow.llm.complete", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope")))
    after = fill_why_now(selected, settings_llm_on)
    assert after[0].opportunity.value == before.opportunity.value
    assert after[0].selected_rank == selected[0].selected_rank
```

- [ ] **Step 2–4: implement with httpx, no official SDK → PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: optional LLM narrative (off by default)"
```

---

### Task 11: 0.1.0 hygiene

**Files:**
- Modify: `CHANGELOG.md`, `README.md`, `src/foreshadow/__init__.py` (`__version__ = "0.1.0"`), `pyproject.toml` version, `PROJECT_STATE.md`, `TODO.md`

**Depends on:** Task 9. Task 10 may or may not be merged.

- [ ] **Step 1: Write a failing version assertion** (optional) or run the full suite as the test:

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run pytest
```

Expected: all green, no network.

- [ ] **Step 2: Set version 0.1.0**, changelog Keep-a-Changelog entry: GET-only radar, empty Top 5, v7 required, human review.

- [ ] **Step 3: Re-run full suite — PASS**

- [ ] **Step 4: Stop.** Use the tool for a week before P1. Do not tag PyPI/Homebrew in P0 unless the owner asks.

- [ ] **Step 5: Commit**

```bash
git commit -am "chore: release 0.1.0"
```

---

## Merge order

```
1 → 2 → (3 → 4 → 5 ∥ 6) → 7 → 8 → 9 → 11
                              └→ 10 optional
```

Task 5 is the highest-risk product PR. Do not start Task 7 until Task 5’s worked examples pass.

## Spec coverage (self-review)

| Spec requirement | Task |
|---|---|
| Skeleton, README v7 caveat, CI, MIT | 1 |
| Config, SQLite v1, models, packaged SQL | 2 |
| Windows, NA, README/tree | 3 |
| H1–H10, H7 fold both sides, direction | 4 |
| Scores, select, 12.A/B/C, cold start, exceptional | 5 |
| GET-only client, documents, denylist | 6 |
| Cap 120 first, identity, Phase B, snapshots, traps | 7 |
| Report + run/report/show, degraded predicate | 8 |
| Review/Enter/watchlist | 9 |
| LLM narrative, cannot change scores | 10 |
| 0.1.0 | 11 |
| No GitHub writes / no padding / no commit KPI | 5, 6, 8 |
| Entered repos do not consume Phase B | 7 |
| `search_capped` is not degraded | 7, 8 |

No P1 multi-source, no dashboard, no auto-PR.
