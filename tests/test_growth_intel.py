"""Growth Intelligence invariants. Contribution scoring is not under test."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from foreshadow.work_order import WorkOrderError, validate

AS_OF = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
OBS = "2026-10-04T10:26:52Z"
SHA = "6948f7522a0a98d4f7d2619583e1b717b9363162"


def _repo(**overrides):
    row = {
        "identity": "acme/tool",
        "role": "owned",
        "archetype": "cli-local",
        "matched_to": None,
        "match_quality": None,
        "maintainer_class": "solo",
        "brand_advantage": "low",
        "created_at": "2026-08-15T13:17:47Z",
        "stars": 3,
        "forks": 0,
        "observation_time": OBS,
        "source_url": "https://github.com/acme/tool",
        "default_branch_sha": SHA,
        "readme_blob_sha": "2e4212dd400678a7bd3be2a947ea1e74680a8602",
        "readme_scope": "CURRENT_SNAPSHOT",
        "selection": "RETROSPECTIVE_SELECTION",
        "release_blocked": False,
        "description_states_job": True,
        "topics_present": True,
        "one_command_install": True,
        "install_paths_conflict": True,
        "demo_present": True,
        "html_url": "https://github.com/acme/tool",
    }
    row.update(overrides)
    return row


def _book(*repos, ceiling="HYPOTHESIS"):
    return {
        "schema": "foreshadow.growth-casebook",
        "version": 1,
        "observation_time": OBS,
        "selection": "RETROSPECTIVE_SELECTION",
        "epistemic_ceiling": ceiling,
        "repositories": list(repos),
    }


def test_elapsed_days_use_calendar_dates_not_sample_count():
    from foreshadow.growth_intel.metrics import star_window

    window = star_window(
        [
            {"date": "2026-09-01", "stars": 10},
            {"date": "2026-09-13", "stars": 22},
        ],
        as_of=date(2026, 10, 4),
    )
    assert window["points"] == 2
    assert window["elapsed_days"] == 12
    assert window["elapsed_days"] != window["points"]
    assert window["delta"] == 12
    assert window["per_day"] == 1


def test_missing_star_counts_stay_missing():
    from foreshadow.growth_intel.metrics import log_growth, star_window

    assert log_growth(None, 10) is None
    assert log_growth(10, None) is None
    window = star_window(
        [
            {"date": "2026-09-01", "stars": None},
            {"date": "2026-09-08", "stars": 4},
        ],
        as_of=date(2026, 10, 4),
    )
    assert window["delta"] is None
    assert window["per_day"] is None
    assert window["log_growth"] is None
    assert 0 not in (window["delta"], window["log_growth"])


def test_future_observation_is_rejected():
    from foreshadow.growth_intel.metrics import star_window

    with pytest.raises(ValueError, match="future"):
        star_window(
            [
                {"date": "2026-10-01", "stars": 1},
                {"date": "2026-10-06", "stars": 9},
            ],
            as_of=date(2026, 10, 4),
        )


def test_log_growth_matches_log1p_difference():
    import math

    from foreshadow.growth_intel.metrics import log_growth

    assert log_growth(0, 0) == 0
    assert log_growth(3, 3) == 0
    assert log_growth(10, 110) == pytest.approx(math.log1p(110) - math.log1p(10))


def test_cohort_selection_is_deterministic():
    from foreshadow.growth_intel.cohort import select_cohort

    cases = [
        _repo(identity="b/second", role="control", matched_to="z/big", brand_advantage="low"),
        _repo(identity="a/first", role="control", matched_to="z/big", brand_advantage="low"),
        _repo(identity="m/brand", role="breakout", brand_advantage="high", matched_to=None),
        _repo(identity="o/mine", role="owned"),
    ]
    first = select_cohort(cases, archetype="cli-local")
    second = select_cohort(list(reversed(cases)), archetype="cli-local")
    assert first == second
    assert first["members"] == ["a/first", "b/second"]
    assert ("m/brand", "brand") in first["excluded"]
    assert ("o/mine", "owned") in first["excluded"]


def test_repository_identity_must_be_owner_name():
    from foreshadow.growth_intel.casebook import load_casebook

    book = _book(_repo(identity="not a repo"))
    with pytest.raises(ValueError, match="identity"):
        load_casebook(book)


def test_provenance_requires_source_and_observation_time():
    from foreshadow.growth_intel.casebook import load_casebook

    book = _book(_repo(source_url="", observation_time=""))
    with pytest.raises(ValueError, match="provenance"):
        load_casebook(book)


def test_stale_evidence_cannot_be_exported():
    from foreshadow.growth_intel.export import export_work_order
    from foreshadow.growth_intel.plan import build_plan

    plan = build_plan(_book(_repo()), as_of=AS_OF)
    with pytest.raises(ValueError, match="stale"):
        export_work_order(plan, now=AS_OF + timedelta(days=30))


def test_owned_repos_are_not_benchmark_members():
    from foreshadow.growth_intel.cohort import select_cohort

    selected = select_cohort([_repo(role="owned")], archetype="cli-local")
    assert selected["members"] == []
    assert selected["excluded"] == [("acme/tool", "owned")]


def test_high_brand_cannot_support_a_transfer():
    from foreshadow.growth_intel.transfer import transfer_for

    result = transfer_for(
        sources=[_repo(identity="github/spec-kit", role="breakout", brand_advantage="high")],
        target=_repo(),
    )
    assert result["band"] == "unknown"
    assert result["status"] == "UNKNOWN"
    assert "brand" in result["why_might_not"].lower()


def test_correlated_status_is_never_causal():
    from foreshadow.growth_intel.models import dump_claim, parse_status

    with pytest.raises(ValueError, match="not a causal"):
        parse_status("CAUSAL")
    with pytest.raises(ValueError, match="not a causal"):
        parse_status("causal")
    claim = dump_claim(
        {
            "id": "cl-1",
            "status": "CORRELATED",
            "text": "Two groups differ. This is not a causal claim.",
            "observation_ids": ["obs-1"],
        }
    )
    assert claim["status"] == "CORRELATED"
    assert "CAUSAL" not in json.dumps(claim)


def test_quasi_experimental_requires_a_dated_event_and_a_control_window():
    from foreshadow.growth_intel.cohort import claim_status

    assert (
        claim_status(
            requested="QUASI_EXPERIMENTAL",
            event=None,
            control_window=None,
            readme_scope="CURRENT_SNAPSHOT",
        )
        == "HYPOTHESIS"
    )
    assert (
        claim_status(
            requested="QUASI_EXPERIMENTAL",
            event={"occurred_at": OBS, "source_url": "https://example.test/release", "type": "RELEASE"},
            control_window={"identity": "acme/control", "elapsed_days": 14},
            readme_scope=None,
        )
        == "QUASI_EXPERIMENTAL"
    )
    assert (
        claim_status(
            requested="QUASI_EXPERIMENTAL",
            event={"occurred_at": OBS, "source_url": "https://example.test/readme", "type": "README"},
            control_window={"identity": "acme/control", "elapsed_days": 14},
            readme_scope="CURRENT_SNAPSHOT",
        )
        == "HYPOTHESIS"
    )


def test_counterevidence_is_retained_on_the_plan():
    from foreshadow.growth_intel.plan import build_plan

    plan = build_plan(_book(_repo()), as_of=AS_OF)
    assert plan["hypothesis"]["counterevidence"]
    encoded = json.dumps(plan)
    assert "counterevidence" in encoded
    assert plan["hypothesis"]["counterevidence"][0] in encoded


def test_experiment_requires_metric_baseline_success_and_failure():
    from foreshadow.growth_intel.plan import validate_experiment

    with pytest.raises(ValueError, match="success_criterion"):
        validate_experiment(
            {
                "id": "gx-1",
                "primary_metric": "install_path_agreement",
                "baseline": "conflict",
                "window_days": 14,
                "failure_criterion": "still conflicts",
                "guardrail": "no release",
            }
        )


def test_star_only_success_is_rejected_below_the_floor():
    from foreshadow.growth_intel.plan import validate_experiment

    with pytest.raises(ValueError, match="underpowered"):
        validate_experiment(
            {
                "id": "gx-stars",
                "primary_metric": "stars",
                "baseline": "3",
                "window_days": 14,
                "success_criterion": "stars >= 30",
                "failure_criterion": "stars unchanged",
                "guardrail": "no solicitation",
            }
        )


def test_plan_json_is_deterministic_and_separates_sections():
    from foreshadow.growth_intel.plan import build_plan
    from foreshadow.growth_intel.render import dumps, render_plan

    plan = build_plan(_book(_repo(), _repo(identity="other/blocked", release_blocked=True, install_paths_conflict=False)), as_of=AS_OF)
    assert dumps(plan) == dumps(plan)
    text = render_plan(plan)
    for heading in ("Fact:", "Interpretation:", "Hypothesis:", "Recommended experiment:"):
        assert heading in text
    assert plan["recommended_experiment"]["target"] == "acme/tool"
    assert plan["recommended_experiment"]["evidence_strength"] == "HYPOTHESIS"
    assert "CAUSAL" not in dumps(plan)


def test_current_readme_cannot_explain_historical_growth():
    from foreshadow.growth_intel.study import build_study

    study = build_study(
        _book(
            _repo(identity="solo/winner", role="breakout", stars=50000, one_command_install=True),
            _repo(
                identity="solo/quiet",
                role="control",
                matched_to="solo/winner",
                stars=40,
                one_command_install=True,
            ),
        ),
        as_of=AS_OF,
    )
    readme_claim = next(item for item in study["claims"] if item["about"] == "readme")
    assert readme_claim["status"] == "UNKNOWN"
    assert "CURRENT_SNAPSHOT" in readme_claim["text"]
    assert all(item["status"] != "QUASI_EXPERIMENTAL" for item in study["claims"])
    assert all(item["status"] != "CORRELATED" for item in study["claims"])


def test_release_blocked_repo_is_not_the_target():
    from foreshadow.growth_intel.portfolio import rank_portfolio

    ranked = rank_portfolio(
        [
            _repo(identity="rainhuang0220/nightshift", release_blocked=True, install_paths_conflict=False),
            _repo(identity="rainhuang0220/whereToken"),
        ]
    )
    assert ranked[0]["identity"] == "rainhuang0220/whereToken"
    assert ranked[0]["eligible"] is True
    blocked = next(item for item in ranked if item["identity"] == "rainhuang0220/nightshift")
    assert blocked["eligible"] is False
    assert blocked["reason"] == "release-blocked"


def test_export_preserves_generic_work_order_semantics(tmp_path: Path):
    from foreshadow.growth_intel.export import export_work_order
    from foreshadow.growth_intel.plan import build_plan

    plan = build_plan(_book(_repo()), as_of=AS_OF)
    order = export_work_order(
        plan,
        now=AS_OF,
        repository_path=tmp_path,
    )
    validated = validate(order)
    assert validated["schema"] == "engineering.work-order"
    assert validated["version"] == 1
    assert type(validated["version"]) is int
    assert validated["repository"]["identity"] == "acme/tool"
    assert validated["repository"]["base_revision"] == SHA
    assert validated["actions"]["allowed"] == ["read", "edit", "commit"]
    assert set(validated["actions"]["forbidden"]) >= {
        "push",
        "publish",
        "deploy",
        "credentials",
        "external-write",
    }
    assert validated["provenance"]["opportunity_id"] == plan["recommended_experiment"]["id"]
    assert "This is not a causal claim." in validated["rationale"]
    assert plan["hypothesis"]["counterevidence"][0] in validated["rationale"]
    assert all(item["kind"] in {"observation", "inference"} for item in validated["evidence"])
    kinds = {item["kind"] for item in validated["evidence"]}
    assert kinds == {"observation", "inference"}
    assert "growth_only" not in validated
    assert "acme/tool" in validated["evidence"][0]["summary"]
    observed = [item for item in validated["evidence"] if item["kind"] == "observation"]
    assert observed
    assert all(item["observed_at"] for item in observed)
    broken = json.loads(json.dumps(validated))
    broken["version"] = 2
    with pytest.raises(WorkOrderError, match="unsupported work-order"):
        validate(broken)


def test_export_refuses_a_different_repository():
    from foreshadow.growth_intel.export import export_work_order
    from foreshadow.growth_intel.plan import build_plan

    plan = build_plan(_book(_repo()), as_of=AS_OF)
    plan["recommended_experiment"]["target"] = "other/repo"
    with pytest.raises(ValueError, match="identity"):
        export_work_order(plan, now=AS_OF)


def test_shipped_casebook_ranks_where_token_and_blocks_nightshift():
    from foreshadow.growth_intel.casebook import packaged_casebook
    from foreshadow.growth_intel.plan import build_plan

    book = packaged_casebook()
    identities = [row["identity"] for row in book["repositories"]]
    assert 24 <= len(identities) <= 40
    assert len(identities) == len(set(identities))
    assert any(row["role"] == "control" and row["brand_advantage"] == "low" for row in book["repositories"])
    assert any(row["brand_advantage"] == "high" for row in book["repositories"])
    plan = build_plan(book, as_of=AS_OF)
    assert plan["recommended_experiment"]["target"] == "rainhuang0220/whereToken"
    assert plan["recommended_experiment"]["evidence_strength"] == "HYPOTHESIS"
    night = next(row for row in plan["portfolio"] if row["identity"] == "rainhuang0220/nightshift")
    assert night["eligible"] is False
    assert plan["blocked_experiments"]
    assert all(item["evidence_strength"] != "QUASI_EXPERIMENTAL" for item in plan["backlog"])
