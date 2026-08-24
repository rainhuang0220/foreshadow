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
