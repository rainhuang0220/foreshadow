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
    """Frozen in PR 2. Omitted key = missing (NA), never implicit 0."""

    u_issue: int | None = None
    u_issue_ext: int | None = None
    issue_sample_n: int | None = None
    i_open: int | None = None
    bug_n: int | None = None
    talk_n: int | None = None
    usage_closed_n: int | None = None
    help_n: int | None = None
    unassigned_help: int | None = None
    repeat_clusters: int | None = None
    maint_touch: float | None = None
    health_percentage: float | None = None
    readme_install: bool | None = None
    screenshot_only: bool | None = None
    readme_excerpt: str | None = None
    readme_headings: list[str] | None = None
    gap_ci: int | None = None
    gap_tests: int | None = None
    gap_docs: int | None = None
    gap_tests_scope: Literal["root_only"] | None = None
    tree_kind: str | None = None
    tree_names: list[str] | None = None
    has_workflows: bool | None = None
    help_issue_titles: list[str] | None = None
    open_issue_titles: list[str] | None = None
    bots_dropped: list[str] | None = None
    phase: Literal["A", "B", "M"] | None = None
    pr_merged_sample_n: int | None = None
    pr_external_merged_n: int | None = None
    pr_accept_rate: float | None = None
    pr_reviewed_n: int | None = None
    pr_review_rate: float | None = None
    maint_first_response_hours: float | None = None
    commits_7d: int | None = None
    commits_30d: int | None = None
    recent_contributors_7d: int | None = None
    releases_30d: int | None = None
    issues_created_7d: int | None = None
    issues_created_30d: int | None = None
    prs_created_7d: int | None = None
    prs_created_30d: int | None = None
    data_completeness: Literal["high", "medium", "low"] | None = None


class ReportJSON(BaseModel):
    """Frozen in PR 2. See Report markdown format for required keys."""

    date: str
    status: Literal["complete", "degraded", "failed"]
    reason: str | None = None
    top5_count: int
    candidate_count: int
    scored_count: int
    budget_used: int
    budget_cap: int
    budget_rest_used: int
    snapshot_days: int
    cards: list[dict]
    active: list[dict]
    watchlist_appendix: list[dict]
    below_bar: list[dict]
    rejected_counts: dict[str, int]
    source_health: dict
