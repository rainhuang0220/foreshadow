import importlib.resources
import tomllib

import pytest
from pydantic import ValidationError

from foreshadow.models import FeaturesBlob, ReportJSON

SPEC_FEATURES = {
    "u_issue": 28,
    "u_issue_ext": 22,
    "issue_sample_n": 34,
    "i_open": 34,
    "bug_n": 12,
    "talk_n": 20,
    "usage_closed_n": 5,
    "help_n": 4,
    "unassigned_help": 3,
    "repeat_clusters": 1,
    "maint_touch": 0.45,
    "health_percentage": 71,
    "readme_install": True,
    "screenshot_only": False,
    "readme_excerpt": "pip install memkit\n...",
    "readme_headings": ["Install", "Memory API"],
    "gap_ci": 0,
    "gap_tests": 0,
    "gap_docs": 1,
    "gap_tests_scope": "root_only",
    "tree_kind": "has_source",
    "tree_names": ["src", "pyproject.toml", "README.md", "LICENSE"],
    "has_workflows": True,
    "help_issue_titles": ["#12 document eviction", "#18 window overflow"],
    "open_issue_titles": ["crash on eviction"],
    "bots_dropped": ["dependabot[bot]"],
    "phase": "B",
}

REPORT_KEYS = (
    "date",
    "status",
    "reason",
    "top5_count",
    "candidate_count",
    "scored_count",
    "budget_used",
    "budget_cap",
    "budget_rest_used",
    "snapshot_days",
    "cards",
    "active",
    "watchlist_appendix",
    "below_bar",
    "rejected_counts",
    "source_health",
)

DIRECTION_BAGS = {
    "LLM",
    "Agent",
    "MCP",
    "RAG/memory",
    "world-model",
    "eval/tooling",
    "AI infra",
    "Rust/systems",
    "RISC-V",
    "compiler/OS",
}


def test_features_blob_parses_spec_object():
    blob = FeaturesBlob.model_validate(SPEC_FEATURES)
    assert blob.u_issue == 28
    assert blob.u_issue_ext == 22
    assert blob.issue_sample_n == 34
    assert blob.i_open == 34
    assert blob.readme_install is True
    assert blob.health_percentage == 71
    assert blob.gap_tests_scope == "root_only"
    assert blob.phase == "B"
    dumped = blob.model_dump()
    assert set(SPEC_FEATURES) <= set(dumped)
    assert set(dumped) == set(FeaturesBlob.model_fields)
    extra = FeaturesBlob(
        phase="B",
        pr_accept_rate=0.5,
        commits_7d=4,
        data_completeness="high",
    )
    extra_d = extra.model_dump()
    assert extra_d["pr_accept_rate"] == 0.5
    assert extra_d["commits_7d"] == 4
    assert extra_d["data_completeness"] == "high"


def test_features_blob_empty_is_all_missing():
    blob = FeaturesBlob()
    dumped = blob.model_dump()
    assert dumped["u_issue"] is None
    assert dumped["gap_ci"] is None
    assert dumped["readme_headings"] is None
    assert dumped["phase"] is None
    assert "U_issue" not in dumped
    assert set(dumped) == set(FeaturesBlob.model_fields)


def test_report_json_requires_spec_keys():
    with pytest.raises(ValidationError):
        ReportJSON(
            date="2026-08-24",
            reason=None,
            snapshot_days=1,
            cards=[],
            active=[],
            watchlist_appendix=[],
            below_bar=[],
            rejected_counts={},
            source_health={},
        )
    report = ReportJSON(
        date="2026-08-24",
        status="degraded",
        reason=None,
        top5_count=2,
        candidate_count=96,
        scored_count=88,
        budget_used=310,
        budget_cap=800,
        budget_rest_used=88,
        snapshot_days=31,
        cards=[],
        active=[],
        watchlist_appendix=[],
        below_bar=[],
        rejected_counts={"H1": 0},
        source_health={"graphql": "ok"},
    )
    dumped = report.model_dump()
    assert list(dumped) == list(REPORT_KEYS)
    assert dumped["status"] == "degraded"
    assert dumped["top5_count"] == 2


def test_directions_ten_spec_bags():
    text = (
        importlib.resources.files("foreshadow")
        .joinpath("directions.toml")
        .read_text(encoding="utf-8")
    )
    bags = tomllib.loads(text)
    assert set(bags) == DIRECTION_BAGS
    for bag in bags.values():
        assert set(bag) >= {"topics", "keywords", "languages"}
        assert isinstance(bag["topics"], list)
        assert isinstance(bag["keywords"], list)
        assert isinstance(bag["languages"], list)
