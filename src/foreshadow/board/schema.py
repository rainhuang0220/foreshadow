from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DIM_KEYS = (
    "momentum",
    "real_users",
    "contributor_gap",
    "contribution_opportunity",
    "early_entry",
)

Recommendation = Literal[
    "strong_candidate",
    "candidate",
    "watch",
    "pass",
    "reject",
]
Consensus = Literal["HIGH CONSENSUS", "MEDIUM CONSENSUS", "LOW CONSENSUS"]
Disagreement = Literal["HIGH", "MEDIUM", "LOW"]
BoardMode = Literal["official", "provisional"]


class EvidenceItem(BaseModel):
    metric: str
    detail: str
    source: str = "github_snapshot"
    window: str | None = None
    observed: str | None = None
    polarity: Literal["+", "-"] = "+"


class DimensionView(BaseModel):
    key: str
    value: int | None
    max: int = 20
    insufficient_history: bool = False
    why: str = ""


class ReviewerResult(BaseModel):
    reviewer: Literal["trend", "community", "contributor"]
    score: float | None
    dimensions: dict[str, int | None]
    confidence: Literal["low", "medium", "high"]
    evidence: list[EvidenceItem] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendation: Recommendation
    weights: dict[str, int]


class ChairResult(BaseModel):
    score: float | None
    blend_score: float | None
    override: bool = False
    justification: str
    dimensions: dict[str, int | None]
    consensus: Consensus
    disagreement: Disagreement
    spread: float
    stdev: float
    why_selected: str | None = None
    exclusion_reason: str | None = None
    main_risk: str | None = None


class PoolRow(BaseModel):
    rank: int
    full_name: str
    node_id: str | None = None
    stars: int | None = None
    growth_signal: str
    status: str
    vetoed: bool = False
    lightweight_score: float | None = None
    reason: str | None = None


class BoardCard(BaseModel):
    full_name: str
    owner: str
    html_url: str | None = None
    stars: int | None = None
    forks: int | None = None
    contributors: int | None = None
    open_issues: int | None = None
    last_pushed_at: str | None = None
    last_release: str | None = None
    first_seen_at: str | None = None
    description: str | None = None
    language: str | None = None
    list_rank: int | None = None
    official_eligible: bool
    lightweight_score: float | None = None
    trend: ReviewerResult
    community: ReviewerResult
    contributor: ReviewerResult
    chair: ChairResult
    final_score: float | None
    dimensions: dict[str, int | None]
    evidence: list[EvidenceItem] = Field(default_factory=list)
    why_now: str | None = None
    suggested_contribution: str | None = None
    p0_opportunity: float | None = None
    p0_explosion: float | None = None
    p0_contribution: float | None = None
    p0_confidence: Literal["low", "medium", "high"] | None = None
    data_completeness: Literal["high", "medium", "low"] | None = None
    activity_momentum: float | None = None
    activity_class: str | None = None
    activity_confidence: Literal["low", "medium", "high"] | None = None
    activity_concentration: float | None = None
    commits_7d: int | None = None
    commits_30d: int | None = None
    releases_30d: int | None = None
    recent_contributors_7d: int | None = None
    s1_stage: str | None = None
    s1_earlyness: float | None = None
    s1_evidence: float | None = None
    s1_window: float | None = None
    s1_pool: str | None = None
    s1_quadrant: str | None = None
    s1_earlyness_plus: list[str] = Field(default_factory=list)
    s1_earlyness_minus: list[str] = Field(default_factory=list)
    s1_evidence_plus: list[str] = Field(default_factory=list)
    s1_evidence_minus: list[str] = Field(default_factory=list)
    access_score: float | None = None
    access_class: str | None = None
    access_merge_rate: float | None = None
    access_review_rate: float | None = None
    strategy_path: str | None = None
    strategy_summary_zh: str | None = None
    strategy_steps_zh: list[str] = Field(default_factory=list)
    strategy_difficulty: str | None = None
    strategy_effort: str | None = None
    momentum_na: bool = False
    vetoed: bool = False
    veto_reason: str | None = None
    review_commands: dict[str, str] = Field(default_factory=dict)


class BoardDocument(BaseModel):
    date: str
    mode: BoardMode
    mode_reason: str
    discovered: int
    shortlisted: int
    deep_reviewed: int
    official_top5: int
    provisional_count: int
    pool: list[PoolRow]
    shortlist: list[BoardCard]
    deep: list[BoardCard]
    official: list[BoardCard]
    provisional: list[BoardCard]
    generated_from: str = "real_snapshots"
    snapshot_days: int = 1
    extra: dict[str, Any] = Field(default_factory=dict)
