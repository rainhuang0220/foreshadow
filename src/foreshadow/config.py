from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

WEIGHT_KEYS = (
    "momentum_weight",
    "real_user_weight",
    "gap_weight",
    "contribution_opp_weight",
    "early_entry_weight",
    "direction_fit_weight",
    "maintainer_weight",
)

DEFAULT_LANGUAGES = ["Python", "Rust", "TypeScript", "Go", "C++"]

DEFAULT_CONFIG_TOML = """\
# examples/config.toml  — also the documented user schema

[discovery]
star_min = 50                 # legacy config; v2 search uses early/rising bands
star_max = 8000
early_star_min = 10           # Pool A recall only, not a score
early_star_max = 400
rising_star_min = 100         # Pool B recall only
rising_star_max = 3000
pool_a_quota = 40             # max exposure, not a fill target
pool_b_quota = 50
pool_c_quota = 30
per_query_floor = 6
pushed_within_days = 45       # templates {pushed45} = today − this
max_candidates = 120          # union of watchlist + search; underfill is OK
max_deep_hydrate = 30
max_watchlist_deep = 20       # Phase B reserved for rankable watchlist only (watch/interested/investigate); enter does not consume
per_page = 25                 # GraphQL search first:N; do not paginate to 1000
exclude_forks = true          # drop forks in discovery. H2 ALWAYS vetoes Top 5 even if false
exclude_archived = true
# Hydrate/pre-rank language bonus only. NEVER a cartesian product of search × languages.
# Empty = no language bonus. Pool B systems already embeds language:Rust.
languages = ["Python", "Rust", "TypeScript", "Go", "C++"]

[scoring]
# Locked product weights in **points** that MUST sum to 100.
# `momentum_weight = 0.20` is invalid (exit 2). Tests pin these defaults.
momentum_weight = 20
real_user_weight = 15
gap_weight = 15
contribution_opp_weight = 20
early_entry_weight = 15
direction_fit_weight = 10
maintainer_weight = 5
min_opportunity = 55
min_explosion = 35
reject_cooldown_days = 90
later_skip_days = 14
max_per_owner = 2             # diversity in Top 5
window_slack_days = 1         # nearest snapshot ≤ t-N within this slack; else NA

[github]
api_url = "https://api.github.com"
graphql_url = "https://api.github.com/graphql"
api_version = "2026-03-10"
timeout_seconds = 30
budget_graphql_points = 800
budget_rest = 400
max_retries = 3
search_spacing_ms = 2000

[llm]
enabled = false
provider = "openai"           # openai | anthropic | xai | custom
model = ""
base_url = ""                 # custom only
max_calls_per_run = 5         # one OpenAI-compatible call per selected card (≤5 cards)
"""


class DiscoverySettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    star_min: int = 50
    star_max: int = 8000
    early_star_min: int = 10
    early_star_max: int = 400
    rising_star_min: int = 100
    rising_star_max: int = 3000
    pool_a_quota: int = 40
    pool_b_quota: int = 50
    pool_c_quota: int = 30
    per_query_floor: int = 6
    pushed_within_days: int = 45
    max_candidates: int = 120
    max_deep_hydrate: int = 30
    max_watchlist_deep: int = 20
    per_page: int = 25
    exclude_forks: bool = True
    exclude_archived: bool = True
    languages: list[str] = Field(default_factory=lambda: list(DEFAULT_LANGUAGES))


class ScoringSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    momentum_weight: int = 20
    real_user_weight: int = 15
    gap_weight: int = 15
    contribution_opp_weight: int = 20
    early_entry_weight: int = 15
    direction_fit_weight: int = 10
    maintainer_weight: int = 5
    min_opportunity: int = 55
    min_explosion: int = 35
    reject_cooldown_days: int = 90
    later_skip_days: int = 14
    max_per_owner: int = 2
    window_slack_days: int = 1


class GitHubSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    api_url: str = "https://api.github.com"
    graphql_url: str = "https://api.github.com/graphql"
    api_version: str = "2026-03-10"
    timeout_seconds: int = 30
    budget_graphql_points: int = 800
    budget_rest: int = 400
    max_retries: int = 3
    search_spacing_ms: int = 2000


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    provider: str = "openai"
    model: str = ""
    base_url: str = ""
    max_calls_per_run: int = 5


class ReviewerWeightSettings(BaseModel):
    """Five-dimension weights in points; must sum to 100."""

    model_config = ConfigDict(extra="ignore")

    momentum: int = 20
    real_users: int = 20
    contributor_gap: int = 20
    contribution_opportunity: int = 20
    early_entry: int = 20

    def as_dict(self) -> dict[str, int]:
        return {
            "momentum": self.momentum,
            "real_users": self.real_users,
            "contributor_gap": self.contributor_gap,
            "contribution_opportunity": self.contribution_opportunity,
            "early_entry": self.early_entry,
        }


class BoardSettings(BaseModel):
    """P1 Audit Board. Does not change P0 official scoring thresholds."""

    model_config = ConfigDict(extra="ignore")

    shortlist_n: int = 20
    deep_review_n: int = 10
    final_n: int = 5
    chair_blend: float = 0.40
    trend_blend: float = 0.20
    community_blend: float = 0.20
    contributor_blend: float = 0.20
    trend: ReviewerWeightSettings = Field(
        default_factory=lambda: ReviewerWeightSettings(
            momentum=35,
            real_users=15,
            contributor_gap=10,
            contribution_opportunity=15,
            early_entry=25,
        )
    )
    community: ReviewerWeightSettings = Field(
        default_factory=lambda: ReviewerWeightSettings(
            momentum=10,
            real_users=30,
            contributor_gap=30,
            contribution_opportunity=15,
            early_entry=15,
        )
    )
    contributor: ReviewerWeightSettings = Field(
        default_factory=lambda: ReviewerWeightSettings(
            momentum=10,
            real_users=15,
            contributor_gap=15,
            contribution_opportunity=40,
            early_entry=20,
        )
    )


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)
    github: GitHubSettings = Field(default_factory=GitHubSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    board: BoardSettings = Field(default_factory=BoardSettings)


def user_config_path() -> Path:
    env = os.environ.get("FORESHADOW_CONFIG")
    if env:
        return Path(env)
    return Path.home() / ".config" / "foreshadow" / "config.toml"


def ensure_default_config(path: Path) -> None:
    """Write the documented default config if ``path`` does not exist. Never overwrite."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")


def load_config(cwd: Path | None = None) -> Settings:
    """Load Settings: code defaults → user config → ./foreshadow.toml (later wins)."""
    data: dict[str, Any] = Settings().model_dump()
    env_path = os.environ.get("FORESHADOW_CONFIG")
    if env_path:
        data = _deep_merge(data, _read_toml(Path(env_path), required=True))
    else:
        xdg = Path.home() / ".config" / "foreshadow" / "config.toml"
        data = _deep_merge(data, _read_toml(xdg, required=False))
    root = Path(cwd) if cwd is not None else Path.cwd()
    data = _deep_merge(data, _read_toml(root / "foreshadow.toml", required=False))
    _require_weights_sum_100(data.get("scoring", {}))
    try:
        return Settings.model_validate(data)
    except ValidationError:
        print("unreadable config", file=sys.stderr)
        raise SystemExit(2) from None


def _require_weights_sum_100(scoring: dict[str, Any]) -> None:
    try:
        total = sum(scoring[key] for key in WEIGHT_KEYS)
    except (KeyError, TypeError):
        print("scoring weights must sum to 100 (got invalid)", file=sys.stderr)
        raise SystemExit(2) from None
    if total != 100:
        print(f"scoring weights must sum to 100 (got {total})", file=sys.stderr)
        raise SystemExit(2)


def _read_toml(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.is_file():
        if required:
            print(f"unreadable config: {path}", file=sys.stderr)
            raise SystemExit(2)
        return {}
    try:
        with path.open("rb") as fh:
            loaded = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        print(f"unreadable config: {path}", file=sys.stderr)
        raise SystemExit(2) from None
    if not isinstance(loaded, dict):
        print(f"unreadable config: {path}", file=sys.stderr)
        raise SystemExit(2)
    return _strip_token(loaded)


def _strip_token(data: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in data.items() if k != "token"}
    github = out.get("github")
    if isinstance(github, dict) and "token" in github:
        out["github"] = {k: v for k, v in github.items() if k != "token"}
    return out


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged
