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
        "surface_discrepancy": {
            "kind": "install_surface_version",
            "observed": "1.2.3",
            "expected": "9.9.9",
            "affected_surfaces": ["docs/INSTALL.md"],
            "evidence": "docs/INSTALL.md names 1.2.3. The release names 9.9.9.",
        },
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

    with pytest.raises(ValueError, match="policy floor"):
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


def _package_sources() -> list[Path]:
    root = Path(__file__).resolve().parents[1] / "src" / "foreshadow" / "growth_intel"
    return sorted(root.glob("*.py"))


def test_generic_planner_has_no_where_token_version_knowledge():
    banned = ("v0.7.6", "v0.7.7", "Formula/wheretoken.rb", "wheretoken")
    offenders = []
    for path in _package_sources():
        text = path.read_text(encoding="utf-8").lower()
        for token in banned:
            if token.lower() in text:
                offenders.append(f"{path.name}:{token}")
    assert offenders == []


def test_synthetic_repository_gets_the_same_treatment_class():
    from foreshadow.growth_intel.plan import build_plan

    plan = build_plan(_book(_repo()), as_of=AS_OF)
    experiment = plan["recommended_experiment"]
    assert experiment["kind"] == "treatment"
    assert experiment["role"] == "treatment-integrity"
    assert experiment["state"] == "TREATMENT_READY"
    assert experiment["implementation_metric"] == "install_path_agreement"
    assert experiment["outcome_metric"] is None
    assert "window_days" not in experiment
    assert "9.9.9" in experiment["success_criterion"]
    assert "1.2.3" in experiment["success_criterion"]
    assert "docs/INSTALL.md" in experiment["success_criterion"]
    assert "v0.7" not in json.dumps(experiment)
    growth = plan["growth_experiment"]
    assert growth["id"] == "gx-qualified-traffic-v1"
    assert growth["kind"] == "outcome"
    assert growth["outcome_metric"] == "daily_unique_visitors"
    assert growth["secondary_metrics"] == ["daily_unique_cloners"]
    assert growth["outcome_metric"] != "unique_visitors"
    assert "rolling" not in growth["outcome_metric"]
    assert "are not summed" in growth["text"]
    assert growth["state"] == "INSUFFICIENT_BASELINE"
    assert growth["interpretation"] == "UNKNOWN"
    assert growth["baseline_observations"] == []
    assert growth["evidence_strength"] == "UNKNOWN"
    assert growth["exportable"] is False
    assert growth["causal"] is False
    assert growth["low_power"] is True
    assert "EXPERIMENT_RESULT" not in json.dumps(plan)


def test_treatment_acceptance_is_not_an_outcome_window():
    from foreshadow.growth_intel.plan import validate_experiment

    with pytest.raises(ValueError, match="not an outcome window"):
        validate_experiment(
            {
                "id": "gx-surface-agreement",
                "kind": "treatment",
                "implementation_metric": "install_path_agreement",
                "baseline": "surfaces disagree",
                "window_days": 14,
                "success_criterion": "the files agree",
                "failure_criterion": "the files still disagree",
                "guardrail": "no release",
            }
        )


def test_implementation_pass_is_not_an_experiment_result():
    from foreshadow.growth_intel.outcome import mark_implementation

    experiment = {"kind": "treatment", "evidence_strength": "HYPOTHESIS", "id": "gx-1"}
    marked = mark_implementation(experiment, passed=True)
    assert marked["state"] == "READY_FOR_OBSERVATION"
    assert marked["implementation"] == "PASS"
    assert marked["evidence_strength"] == "HYPOTHESIS"
    poisoned = dict(experiment, evidence_strength="EXPERIMENT_RESULT")
    with pytest.raises(ValueError, match="not an experiment result"):
        mark_implementation(poisoned, passed=True)


def test_measured_change_keeps_raw_observations_and_is_not_causal():
    from foreshadow.growth_intel.outcome import measure_outcome

    baseline = [{"observed_on": "2026-09-01", "daily_unique_visitors": 6, "clones": 1}]
    post = [
        {"observed_on": "2026-09-10", "daily_unique_visitors": 6, "clones": 1},
        {"observed_on": "2026-09-22", "daily_unique_visitors": 18, "clones": 5},
    ]
    result = measure_outcome(
        baseline=baseline,
        post=post,
        intervention_on="2026-09-10",
        as_of=AS_OF,
    )
    assert result["state"] == "MEASURED"
    assert result["evidence_strength"] == "OBSERVED"
    assert result["interpretation"] == "OBSERVED_CHANGE"
    assert result["causal"] is False
    assert result["metric"] == "daily_unique_visitors"
    assert result["comparison"] == "last_daily_unique_visitors"
    assert result["before_daily_unique_visitors"] == 6
    assert result["after_daily_unique_visitors"] == 18
    assert "are not summed" in result["text"]
    assert "rolling 14-day" in result["text"]
    assert result["elapsed_days"] == 12
    assert result["elapsed_days"] != len(post)
    assert result["baseline_observations"] == baseline
    assert result["post_observations"] == post
    unordered = measure_outcome(
        baseline=[
            {"observed_on": "2026-09-08", "daily_unique_visitors": 1},
            {"observed_on": "2026-09-01", "daily_unique_visitors": 18},
        ],
        post=[
            {"observed_on": "2026-09-22", "daily_unique_visitors": 1},
            {"observed_on": "2026-09-10", "daily_unique_visitors": 9},
        ],
        intervention_on="2026-09-10",
        as_of=AS_OF,
    )
    assert unordered["interpretation"] == "NO_CLEAR_CHANGE"
    assert unordered["before_daily_unique_visitors"] == 1
    assert unordered["after_daily_unique_visitors"] == 1
    assert unordered["baseline_observations"][0]["daily_unique_visitors"] == 1
    assert "QUASI_EXPERIMENTAL" not in result.values()
    assert "EXPERIMENT_RESULT" not in result.values()
    assert "not a causal claim" in result["text"]


def test_insufficient_baseline_stays_explicit():
    from foreshadow.growth_intel.outcome import measure_outcome

    post = [
        {"observed_on": "2026-09-10", "daily_unique_visitors": 1},
        {"observed_on": "2026-09-12", "daily_unique_visitors": 2},
    ]
    missing = measure_outcome(
        baseline=[],
        post=post,
        intervention_on="2026-09-10",
        as_of=AS_OF,
    )
    assert missing["state"] == "INSUFFICIENT_BASELINE"
    assert missing["evidence_strength"] == "UNKNOWN"
    assert missing["elapsed_days"] is None
    assert missing["post_observations"] == post
    short = measure_outcome(
        baseline=[{"observed_on": "2026-09-01", "daily_unique_visitors": 1}],
        post=[{"observed_on": "2026-09-12", "daily_unique_visitors": 2}],
        intervention_on="2026-09-10",
        as_of=AS_OF,
    )
    assert short["state"] == "INSUFFICIENT_BASELINE"
    assert short["elapsed_days"] is None
    same_day = measure_outcome(
        baseline=[{"observed_on": "2026-09-01", "daily_unique_visitors": 1}],
        post=[
            {"observed_on": "2026-09-10T00:00:00Z", "daily_unique_visitors": 1},
            {"observed_on": "2026-09-10T18:00:00Z", "daily_unique_visitors": 4},
        ],
        intervention_on="2026-09-10",
        as_of=AS_OF,
    )
    assert same_day["state"] == "INSUFFICIENT_BASELINE"
    assert same_day["elapsed_days"] in (None, 0)


def test_missing_outcome_counts_are_not_zero():
    from foreshadow.growth_intel.outcome import measure_outcome

    result = measure_outcome(
        baseline=[{"observed_on": "2026-09-01"}],
        post=[
            {"observed_on": "2026-09-10", "daily_unique_visitors": None},
            {"observed_on": "2026-09-22"},
        ],
        intervention_on="2026-09-10",
        as_of=AS_OF,
    )
    assert result["state"] == "MEASURED"
    assert result["interpretation"] == "UNKNOWN"
    assert result["causal"] is False
    assert result["metric"] == "daily_unique_visitors"
    assert result["before_daily_unique_visitors"] is None
    assert result["after_daily_unique_visitors"] is None


def test_daily_uniques_are_not_summed_or_read_as_window_uniques():
    from foreshadow.growth_intel.outcome import measure_outcome

    summed = measure_outcome(
        baseline=[
            {"observed_on": "2026-09-01", "daily_unique_visitors": 2},
            {"observed_on": "2026-09-03", "daily_unique_visitors": 3},
        ],
        post=[
            {"observed_on": "2026-09-10", "daily_unique_visitors": 4},
            {"observed_on": "2026-09-12", "daily_unique_visitors": 6},
        ],
        intervention_on="2026-09-10",
        as_of=AS_OF,
    )
    assert summed["before_daily_unique_visitors"] == 3
    assert summed["after_daily_unique_visitors"] == 6
    assert summed["interpretation"] == "OBSERVED_CHANGE"
    assert 5 not in summed.values()
    assert 10 not in summed.values()
    ignored = measure_outcome(
        baseline=[
            {
                "observed_on": "2026-09-01",
                "daily_unique_visitors": 1,
                "rolling_14d_unique_visitors": 50,
                "unique_visitors": 50,
            },
            {
                "observed_on": "2026-09-03",
                "daily_unique_visitors": 1,
                "rolling_14d_unique_visitors": 80,
                "unique_visitors": 80,
            },
        ],
        post=[
            {
                "observed_on": "2026-09-10",
                "daily_unique_visitors": 1,
                "rolling_14d_unique_visitors": 10,
                "unique_visitors": 10,
            },
            {
                "observed_on": "2026-09-12",
                "daily_unique_visitors": 1,
                "rolling_14d_unique_visitors": 90,
                "unique_visitors": 90,
            },
        ],
        intervention_on="2026-09-10",
        as_of=AS_OF,
    )
    assert ignored["interpretation"] == "NO_CLEAR_CHANGE"
    assert ignored["before_daily_unique_visitors"] == 1
    assert ignored["after_daily_unique_visitors"] == 1
    ambiguous = measure_outcome(
        baseline=[{"observed_on": "2026-09-01", "unique_visitors": 1}],
        post=[
            {"observed_on": "2026-09-10", "unique_visitors": 4},
            {"observed_on": "2026-09-12", "unique_visitors": 40},
        ],
        intervention_on="2026-09-10",
        as_of=AS_OF,
    )
    assert ambiguous["state"] == "MEASURED"
    assert ambiguous["interpretation"] == "UNKNOWN"
    assert ambiguous["before_daily_unique_visitors"] is None
    assert ambiguous["after_daily_unique_visitors"] is None


def test_future_outcome_observation_is_rejected():
    from foreshadow.growth_intel.outcome import measure_outcome

    with pytest.raises(ValueError, match="future"):
        measure_outcome(
            baseline=[{"observed_on": "2026-10-06", "daily_unique_visitors": 1}],
            post=[],
            intervention_on="2026-10-01",
            as_of=AS_OF,
        )


def test_transfer_does_not_infer_a_band_from_an_editable_file():
    from foreshadow.growth_intel.transfer import transfer_for

    result = transfer_for(
        sources=[
            _repo(
                identity="solo/quiet",
                role="control",
                brand_advantage="low",
                matched_to="acme/tool",
                created_at="2016-03-11T00:00:00Z",
                archetype="cli-local",
            )
        ],
        target=_repo(archetype="portfolio"),
        as_of=AS_OF,
    )
    assert result["band"] == "unknown"
    assert result["status"] == "UNKNOWN"
    assert result["assessment"]["age_compatibility"] == "not_comparable"
    assert result["assessment"]["archetype"] == "mixed"
    assert result["assessment"]["measurement_quality"] == "unknown"
    assert "effect size" in result["why_might_not"].lower()


def test_portfolio_priority_is_not_a_growth_score():
    from foreshadow.growth_intel.portfolio import rank_portfolio

    ranked = rank_portfolio(
        [
            _repo(identity="rainhuang0220/whereToken"),
            _repo(
                identity="rainhuang0220/foreshadow",
                install_paths_conflict=False,
                description_states_job=False,
                demo_present=False,
                topics_present=False,
            ),
            _repo(
                identity="rainhuang0220/nightshift",
                release_blocked=True,
                install_paths_conflict=False,
            ),
        ]
    )
    winner = ranked[0]
    assert winner["identity"] == "rainhuang0220/whereToken"
    assert "score" not in winner
    assert winner["intervention_priority"] == 5
    assert winner["priority_meaning"] == "actionable-friction"
    second = next(item for item in ranked if item["identity"] == "rainhuang0220/foreshadow")
    assert second["intervention_priority"] == 4
    blocked = next(item for item in ranked if item["identity"] == "rainhuang0220/nightshift")
    assert blocked["eligible"] is False
    assert blocked["reason"] == "release-blocked"
    assert blocked["intervention_priority"] is None
    assert blocked["priority_meaning"] == "actionable-friction"
    encoded = json.dumps(ranked)
    assert "star potential" not in encoded
    assert "expected_entry" not in encoded


def test_external_description_change_has_no_outcome_window():
    from foreshadow.growth_intel.plan import build_plan

    plan = build_plan(
        _book(
            _repo(
                identity="acme/docs",
                description_states_job=False,
                install_paths_conflict=False,
                demo_present=False,
                topics_present=True,
            )
        ),
        as_of=AS_OF,
    )
    assert plan["recommended_experiment"] is None
    item = plan["backlog"][0]
    assert item["id"] == "gx-explicit-header-v1"
    assert item["kind"] == "treatment"
    assert "window_days" not in item
    assert item["exportable"] is False
    assert item["reason"] == "external-write"


def test_export_uses_the_observation_discrepancy(tmp_path: Path):
    from foreshadow.growth_intel.export import export_work_order
    from foreshadow.growth_intel.plan import build_plan

    secret = "ghp_OWNER_TRAFFIC_SECRET"
    plan = build_plan(_book(_repo()), as_of=AS_OF)
    order = export_work_order(plan, now=AS_OF, repository_path=tmp_path)
    encoded = json.dumps(order)
    assert "9.9.9" in order["objective"]
    assert "docs/INSTALL.md" in order["objective"]
    assert order["validation"][0]["argv"] == [
        "git",
        "grep",
        "-n",
        "-F",
        "-e",
        "9.9.9",
        "--",
        "docs/INSTALL.md",
    ]
    assert "v0.7.6" not in encoded
    assert "Formula/wheretoken.rb" not in encoded
    assert secret not in encoded
    refused = dict(plan)
    refused["recommended_experiment"] = plan["growth_experiment"]
    with pytest.raises(ValueError, match="cannot be a work order"):
        export_work_order(refused, now=AS_OF)


def test_where_token_discrepancy_stays_in_the_casebook():
    from foreshadow.growth_intel.casebook import packaged_casebook
    from foreshadow.growth_intel.plan import build_plan

    book = packaged_casebook()
    where = next(row for row in book["repositories"] if row["identity"] == "rainhuang0220/whereToken")
    assert where["treatment_id"] == "gx-single-install-path-v1"
    assert where["surface_discrepancy"]["observed"] == "v0.7.6"
    assert where["surface_discrepancy"]["expected"] == "v0.7.7"
    assert where["surface_discrepancy"]["affected_surfaces"] == [
        "Formula/wheretoken.rb",
        "README.md",
    ]
    others = [row for row in book["repositories"] if "surface_discrepancy" in row]
    assert [row["identity"] for row in others] == ["rainhuang0220/whereToken"]
    plan = build_plan(book, as_of=AS_OF)
    experiment = plan["recommended_experiment"]
    assert experiment["id"] == "gx-single-install-path-v1"
    assert experiment["kind"] == "treatment"
    assert experiment["state"] == "TREATMENT_READY"
    assert "window_days" not in experiment
    assert plan["growth_experiment"]["target"] == "rainhuang0220/whereToken"
    assert plan["growth_experiment"]["state"] == "INSUFFICIENT_BASELINE"
    assert plan["growth_experiment"]["baseline_observations"] == []
    night = next(row for row in plan["portfolio"] if row["identity"] == "rainhuang0220/nightshift")
    assert night["reason"] == "release-blocked"
    assert plan["transferability"]["status"] == "UNKNOWN"
    assert plan["transferability"]["band"] == "unknown"


def test_growth_modules_do_not_import_contribution_ranking():
    import ast

    banned_prefixes = (
        "foreshadow.score",
        "foreshadow.score_v2",
        "foreshadow.pipeline",
        "foreshadow.learning",
        "foreshadow.decision",
    )
    for path in _package_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(banned_prefixes), path.name


def test_public_client_still_denies_traffic():
    from foreshadow.github.client import rest_path_denied

    assert rest_path_denied("https://api.github.com/repos/acme/tool/traffic/views")
    assert rest_path_denied("https://api.github.com/repos/acme/tool/traffic/clones")
    assert rest_path_denied("https://api.github.com/repos/acme/tool/traffic/popular/referrers")
    assert rest_path_denied("https://api.github.com/repos/acme/tool/traffic/popular/paths")


def test_traffic_missing_days_are_not_zero_and_future_days_are_rejected():
    from foreshadow.growth_intel.owner_traffic import parse_daily

    rows = parse_daily(
        {
            "count": 9,
            "uniques": 4,
            "views": [
                {"timestamp": "2026-09-20T00:00:00Z", "count": 1, "uniques": 1},
                {"timestamp": "2026-09-22T00:00:00Z", "uniques": 2},
            ],
        },
        series="views",
        now=AS_OF,
    )
    assert [row["observed_on"] for row in rows] == ["2026-09-20", "2026-09-22"]
    assert rows[1]["count"] is None
    assert rows[1]["uniques"] == 2
    assert all(row["count"] != 0 or row["observed_on"] == "2026-09-20" for row in rows)
    assert parse_daily({}, series="views", now=AS_OF) == []
    with pytest.raises(ValueError, match="future"):
        parse_daily(
            {"views": [{"timestamp": "2026-10-06T00:00:00Z", "count": 1, "uniques": 1}]},
            series="views",
            now=AS_OF,
        )


def test_owner_token_is_not_stored_or_exported(tmp_path: Path, monkeypatch):
    from foreshadow.db import connect, migrate
    from foreshadow.growth_intel.export import export_work_order
    from foreshadow.growth_intel.owner_traffic import record_owner_traffic
    from foreshadow.growth_intel.plan import build_plan

    secret = "ghp_OWNER_TRAFFIC_SECRET"
    monkeypatch.setenv("FORESHADOW_OWNER_TRAFFIC_TOKEN", secret)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_BROAD_LOGIN_SECRET")

    class _Body:
        def __init__(self, payload: bytes):
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _Opener:
        def __init__(self):
            self.urls = []

        def open(self, request, timeout=None):
            self.urls.append(request.full_url)
            if request.full_url.endswith("/traffic/views?per=day"):
                payload = {
                    "count": 4,
                    "uniques": 2,
                    "views": [
                        {"timestamp": "2026-09-20T00:00:00Z", "count": 1, "uniques": 1},
                        {"timestamp": "2026-09-22T00:00:00Z", "count": 0, "uniques": 0},
                    ],
                }
            elif request.full_url.endswith("/traffic/clones?per=day"):
                payload = {
                    "clones": [
                        {"timestamp": "2026-09-20T00:00:00Z", "count": 2, "uniques": 1},
                    ]
                }
            elif request.full_url.endswith("/traffic/popular/referrers"):
                payload = [{"referrer": "github.com", "count": 2, "uniques": 1}]
            elif request.full_url.endswith("/traffic/popular/paths"):
                payload = [{"path": "/acme/tool", "count": 3, "uniques": 1}]
            else:
                raise AssertionError(request.full_url)
            assert secret in request.get_header("Authorization")
            return _Body(json.dumps(payload).encode())

    opener = _Opener()
    db_path = tmp_path / "owner.sqlite3"
    conn = connect(db_path)
    migrate(conn)
    record_owner_traffic(
        conn,
        identity="acme/tool",
        token=secret,
        allowed={"acme/tool"},
        opener=opener,
        clock=lambda: AS_OF,
    )
    stored = conn.execute(
        "SELECT source, observed_on, metric, value FROM owner_traffic_observations ORDER BY source, metric, observed_on"
    ).fetchall()
    assert ("views", "2026-09-21", "daily_views", 0) not in stored
    assert ("views", "2026-09-22", "daily_views", 0) in stored
    assert ("views", "2026-09-22", "daily_unique_visitors", 0) in stored
    assert ("views", "2026-10-04", "rolling_14d_unique_visitors", 2) in stored
    assert ("views", "2026-10-04", "rolling_14d_unique_visitors", 1) not in stored
    assert ("clones", "2026-09-20", "daily_unique_cloners", 1) in stored
    assert all(metric != "rolling_14d_unique_cloners" for _, _, metric, _ in stored)
    assert ("referrers", "2026-10-04", "window_count:github.com", 2) in stored
    provenance = conn.execute(
        """
        SELECT identity, source, observed_on, metric, value, fetched_at, grain
        FROM owner_traffic_observations
        """
    ).fetchall()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(owner_traffic_observations)")}
    assert "token" not in columns
    assert {"identity", "source", "observed_on", "metric", "value", "fetched_at", "grain"} <= columns
    for identity, source, observed_on, metric, _value, fetched_at, grain in provenance:
        assert identity == "acme/tool"
        assert source in {"views", "clones", "referrers", "paths"}
        assert observed_on
        assert metric
        assert fetched_at == "2026-10-04T12:00:00Z"
        if metric.startswith("daily_"):
            assert grain == "day"
        if metric.startswith("rolling_14d_") or source in {"referrers", "paths"}:
            assert grain == "window"
    assert {row[2] for row in provenance if row[1] == "referrers"} == {"2026-10-04"}
    assert {row[2] for row in provenance if row[1] == "paths"} == {"2026-10-04"}
    blob = db_path.read_bytes()
    assert secret.encode() not in blob
    assert b"ghp_BROAD_LOGIN_SECRET" not in blob
    plan = build_plan(_book(_repo()), as_of=AS_OF)
    order = export_work_order(plan, now=AS_OF, repository_path=tmp_path)
    encoded = json.dumps(plan) + json.dumps(order)
    assert secret not in encoded
    assert "ghp_BROAD_LOGIN_SECRET" not in encoded
    with pytest.raises(ValueError, match="configured owned"):
        record_owner_traffic(
            conn,
            identity="other/repo",
            token=secret,
            allowed={"acme/tool"},
            opener=opener,
            clock=lambda: AS_OF,
        )


def test_owner_traffic_refuses_redirects_and_redacts_the_token():
    import io
    import urllib.error

    from foreshadow.growth_intel.owner_traffic import _NoRedirect, fetch_json

    with pytest.raises(ValueError, match="redirected"):
        _NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.example/steal")
    secret = "ghp_OWNER_TRAFFIC_SECRET"

    class _Boom:
        def open(self, request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url,
                403,
                "no",
                hdrs=None,
                fp=io.BytesIO(f"denied {secret}".encode()),
            )

    with pytest.raises(ValueError, match="redacted") as raised:
        fetch_json("acme/tool", "views", token=secret, opener=_Boom(), allowed={"acme/tool"})
    assert secret not in str(raised.value)


def _traffic_conn(tmp_path: Path):
    from foreshadow.db import connect, migrate

    conn = connect(tmp_path / "traffic.sqlite3")
    migrate(conn)
    return conn


def _window_values(conn, *, identity: str, source: str, observed_on: str) -> dict[str, dict[str, int | None]]:
    rows = conn.execute(
        """
        SELECT metric, value FROM owner_traffic_observations
        WHERE identity=? AND source=? AND observed_on=?
        """,
        (identity, source, observed_on),
    ).fetchall()
    found: dict[str, dict[str, int | None]] = {}
    for metric, value in rows:
        kind, separator, label = metric.partition(":")
        if not separator:
            continue
        slot = "count" if kind.endswith("count") else "uniques"
        found.setdefault(label, {})[slot] = value
    return found


def _referrer(name: str, count: int, uniques: int, day: str = "2026-10-04") -> dict:
    return {
        "observed_on": day,
        "referrer": name,
        "count": count,
        "uniques": uniques,
        "grain": "window",
    }


def _path(name: str, count: int, uniques: int, day: str = "2026-10-04") -> dict:
    return {
        "observed_on": day,
        "path": name,
        "count": count,
        "uniques": uniques,
        "grain": "window",
    }


def test_same_day_referrer_refetch_drops_stale_entries(tmp_path: Path):
    from foreshadow.growth_intel.owner_traffic import store_window

    conn = _traffic_conn(tmp_path)
    identity = "acme/tool"
    store_window(
        conn,
        identity=identity,
        source="referrers",
        rows=[_referrer("A", 1, 1), _referrer("B", 2, 2), _referrer("C", 3, 3)],
        fetched_at="2026-10-04T12:00:00Z",
    )
    store_window(
        conn,
        identity=identity,
        source="referrers",
        rows=[_referrer("A", 9, 4), _referrer("D", 8, 5)],
        fetched_at="2026-10-04T13:00:00Z",
    )
    stored = _window_values(conn, identity=identity, source="referrers", observed_on="2026-10-04")
    assert set(stored) == {"A", "D"}
    assert stored["A"] == {"count": 9, "uniques": 4}
    assert stored["D"] == {"count": 8, "uniques": 5}


def test_same_day_path_refetch_drops_stale_entries(tmp_path: Path):
    from foreshadow.growth_intel.owner_traffic import store_window

    conn = _traffic_conn(tmp_path)
    identity = "acme/tool"
    store_window(
        conn,
        identity=identity,
        source="paths",
        rows=[_path("/A", 1, 1), _path("/B", 2, 2), _path("/C", 3, 3)],
        fetched_at="2026-10-04T12:00:00Z",
    )
    store_window(
        conn,
        identity=identity,
        source="paths",
        rows=[_path("/A", 7, 3), _path("/D", 6, 2)],
        fetched_at="2026-10-04T13:00:00Z",
    )
    stored = _window_values(conn, identity=identity, source="paths", observed_on="2026-10-04")
    assert set(stored) == {"/A", "/D"}
    assert stored["/A"]["count"] == 7


def test_window_replacement_keeps_other_dates_and_sources(tmp_path: Path):
    from foreshadow.growth_intel.owner_traffic import store_daily, store_window

    conn = _traffic_conn(tmp_path)
    identity = "acme/tool"
    store_window(
        conn,
        identity=identity,
        source="referrers",
        rows=[_referrer("B", 2, 2, day="2026-10-03")],
        fetched_at="2026-10-03T12:00:00Z",
    )
    store_window(
        conn,
        identity=identity,
        source="paths",
        rows=[_path("/keep", 4, 1)],
        fetched_at="2026-10-04T12:00:00Z",
    )
    store_daily(
        conn,
        identity=identity,
        source="views",
        rows=[{"observed_on": "2026-10-04", "count": 3, "uniques": 1}],
        fetched_at="2026-10-04T12:00:00Z",
    )
    store_window(
        conn,
        identity=identity,
        source="referrers",
        rows=[_referrer("A", 1, 1), _referrer("B", 2, 2), _referrer("C", 3, 3)],
        fetched_at="2026-10-04T12:00:00Z",
    )
    store_window(
        conn,
        identity=identity,
        source="referrers",
        rows=[_referrer("A", 9, 4), _referrer("D", 8, 5)],
        fetched_at="2026-10-04T13:00:00Z",
    )
    assert set(_window_values(conn, identity=identity, source="referrers", observed_on="2026-10-03")) == {"B"}
    assert set(_window_values(conn, identity=identity, source="paths", observed_on="2026-10-04")) == {"/keep"}
    daily = conn.execute(
        """
        SELECT value FROM owner_traffic_observations
        WHERE identity=? AND source='views' AND observed_on='2026-10-04'
          AND metric IN ('views', 'daily_views')
        """,
        (identity,),
    ).fetchone()
    assert daily[0] == 3


def test_failed_window_replacement_restores_the_previous_snapshot(tmp_path: Path):
    import sqlite3

    from foreshadow.growth_intel.owner_traffic import store_window

    conn = _traffic_conn(tmp_path)
    identity = "acme/tool"
    store_window(
        conn,
        identity=identity,
        source="referrers",
        rows=[_referrer("A", 1, 1), _referrer("B", 2, 2), _referrer("C", 3, 3)],
        fetched_at="2026-10-04T12:00:00Z",
    )
    conn.execute(
        """
        CREATE TRIGGER abort_boom
        BEFORE INSERT ON owner_traffic_observations
        WHEN NEW.metric LIKE '%:boom'
        BEGIN
          SELECT RAISE(ABORT, 'injected failure');
        END
        """
    )
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        store_window(
            conn,
            identity=identity,
            source="referrers",
            rows=[_referrer("A", 9, 4), _referrer("boom", 8, 5)],
            fetched_at="2026-10-04T13:00:00Z",
        )
    stored = _window_values(conn, identity=identity, source="referrers", observed_on="2026-10-04")
    assert set(stored) == {"A", "B", "C"}
    assert stored["A"] == {"count": 1, "uniques": 1}
    assert "boom" not in stored


def test_empty_referrer_refetch_clears_only_that_snapshot(tmp_path: Path):
    from foreshadow.growth_intel.owner_traffic import store_window

    conn = _traffic_conn(tmp_path)
    identity = "acme/tool"
    store_window(
        conn,
        identity=identity,
        source="referrers",
        rows=[_referrer("B", 2, 2, day="2026-10-03")],
        fetched_at="2026-10-03T12:00:00Z",
    )
    store_window(
        conn,
        identity=identity,
        source="referrers",
        rows=[_referrer("A", 1, 1), _referrer("B", 2, 2)],
        fetched_at="2026-10-04T12:00:00Z",
        observed_on="2026-10-04",
    )
    store_window(
        conn,
        identity=identity,
        source="referrers",
        rows=[],
        fetched_at="2026-10-04T13:00:00Z",
        observed_on="2026-10-04",
    )
    assert _window_values(conn, identity=identity, source="referrers", observed_on="2026-10-04") == {}
    assert set(_window_values(conn, identity=identity, source="referrers", observed_on="2026-10-03")) == {"B"}


def _payload_opener(payloads: dict[str, object]):
    class _Body:
        def __init__(self, payload: bytes):
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _Opener:
        def open(self, request, timeout=None):
            for suffix, payload in payloads.items():
                if request.full_url.endswith(suffix):
                    return _Body(json.dumps(payload).encode())
            raise AssertionError(request.full_url)

    return _Opener()


def test_rolling_totals_keep_github_uniques_and_explicit_zero(tmp_path: Path):
    from foreshadow.growth_intel.owner_traffic import record_owner_traffic

    conn = _traffic_conn(tmp_path)
    record_owner_traffic(
        conn,
        identity="acme/tool",
        token="ghp_OWNER_TRAFFIC_SECRET",
        allowed={"acme/tool"},
        clock=lambda: AS_OF,
        opener=_payload_opener(
            {
                "/traffic/views?per=day": {
                    "count": 10,
                    "uniques": 5,
                    "views": [
                        {"timestamp": "2026-09-20T00:00:00Z", "count": 2, "uniques": 2},
                        {"timestamp": "2026-09-21T00:00:00Z", "count": 3, "uniques": 3},
                        {"timestamp": "2026-09-22T00:00:00Z", "count": 4, "uniques": 4},
                    ],
                },
                "/traffic/clones?per=day": {
                    "count": 0,
                    "uniques": 0,
                    "clones": [
                        {"timestamp": "2026-09-22T00:00:00Z", "count": 0, "uniques": 0},
                    ],
                },
                "/traffic/popular/referrers": [],
                "/traffic/popular/paths": [{"path": "/readme", "count": 1, "uniques": 1}],
            }
        ),
    )
    stored = {
        (source, day, metric): value
        for source, day, metric, value in conn.execute(
            "SELECT source, observed_on, metric, value FROM owner_traffic_observations"
        )
    }
    assert stored[("views", "2026-10-04", "rolling_14d_unique_visitors")] == 5
    assert stored[("views", "2026-10-04", "rolling_14d_views")] == 10
    assert ("views", "2026-10-04", "rolling_14d_unique_visitors") in stored
    assert 9 not in stored.values()
    assert stored[("clones", "2026-10-04", "rolling_14d_unique_cloners")] == 0
    assert stored[("clones", "2026-10-04", "rolling_14d_clones")] == 0
    assert stored[("clones", "2026-09-22", "daily_clones")] == 0
    assert stored[("views", "2026-09-22", "daily_unique_visitors")] == 4
    day_values = conn.execute(
        """
        SELECT value FROM owner_traffic_observations
        WHERE source='views' AND metric='daily_unique_visitors'
        """
    ).fetchall()
    assert sum(value for (value,) in day_values) == 9
    assert stored[("views", "2026-10-04", "rolling_14d_unique_visitors")] != 9
    missing = _payload_opener(
        {
            "/traffic/views?per=day": {
                "views": [{"timestamp": "2026-09-20T00:00:00Z", "uniques": 2}],
            },
            "/traffic/clones?per=day": {"clones": []},
            "/traffic/popular/referrers": [],
            "/traffic/popular/paths": [],
        }
    )
    fresh = _traffic_conn(tmp_path / "missing")
    record_owner_traffic(
        fresh,
        identity="acme/tool",
        token="ghp_OWNER_TRAFFIC_SECRET",
        allowed={"acme/tool"},
        clock=lambda: AS_OF,
        opener=missing,
    )
    missing_rows = fresh.execute(
        "SELECT metric, value FROM owner_traffic_observations WHERE source='views'"
    ).fetchall()
    assert ("daily_unique_visitors", 2) in missing_rows
    assert ("daily_views", None) in missing_rows
    assert all(not metric.startswith("rolling_14d_") for metric, _value in missing_rows)


def test_future_api_days_are_rejected_before_they_are_stored(tmp_path: Path):
    from foreshadow.growth_intel.owner_traffic import record_owner_traffic

    conn = _traffic_conn(tmp_path)
    with pytest.raises(ValueError, match="future"):
        record_owner_traffic(
            conn,
            identity="acme/tool",
            token="ghp_OWNER_TRAFFIC_SECRET",
            allowed={"acme/tool"},
            clock=lambda: AS_OF,
            opener=_payload_opener(
                {
                    "/traffic/views?per=day": {
                        "count": 1,
                        "uniques": 1,
                        "views": [{"timestamp": "2026-10-06T00:00:00Z", "count": 1, "uniques": 1}],
                    },
                    "/traffic/clones?per=day": {"count": 0, "uniques": 0, "clones": []},
                    "/traffic/popular/referrers": [{"referrer": "A", "count": 1, "uniques": 1}],
                    "/traffic/popular/paths": [],
                }
            ),
        )
    assert conn.execute("SELECT COUNT(*) FROM owner_traffic_observations").fetchone()[0] == 0


def test_fetch_clock_dates_referrers_without_inventing_history(tmp_path: Path):
    from foreshadow.growth_intel.owner_traffic import record_owner_traffic

    moment = datetime(2026, 5, 1, 8, 30, tzinfo=UTC)
    conn = _traffic_conn(tmp_path)
    record_owner_traffic(
        conn,
        identity="acme/tool",
        token="ghp_OWNER_TRAFFIC_SECRET",
        allowed={"acme/tool"},
        clock=lambda: moment,
        opener=_payload_opener(
            {
                "/traffic/views?per=day": {
                    "count": 3,
                    "uniques": 2,
                    "views": [{"timestamp": "2026-04-20T00:00:00Z", "count": 3, "uniques": 2}],
                },
                "/traffic/clones?per=day": {"clones": []},
                "/traffic/popular/referrers": [
                    {"referrer": "A", "count": 1, "uniques": 1},
                    {"referrer": "D", "count": 1, "uniques": 1},
                ],
                "/traffic/popular/paths": [],
            }
        ),
    )
    referrer_days = {
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT observed_on FROM owner_traffic_observations WHERE source='referrers'"
        )
    }
    assert referrer_days == {"2026-05-01"}
    fetched = {
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT fetched_at FROM owner_traffic_observations WHERE source='referrers'"
        )
    }
    assert fetched == {"2026-05-01T08:30:00Z"}
    assert conn.execute(
        "SELECT observed_on FROM owner_traffic_observations WHERE metric='daily_views'"
    ).fetchone()[0] == "2026-04-20"
    with pytest.raises(TypeError):
        record_owner_traffic(
            conn,
            identity="acme/tool",
            token="ghp_OWNER_TRAFFIC_SECRET",
            allowed={"acme/tool"},
            as_of=moment,
        )


def test_observe_rejects_a_backdated_fetch_and_uses_the_process_clock(monkeypatch, tmp_path: Path):
    from typer.testing import CliRunner

    from foreshadow.cli import app
    from foreshadow.db import connect

    secret = "ghp_OWNER_TRAFFIC_SECRET"
    monkeypatch.setenv("FORESHADOW_OWNER_TRAFFIC_TOKEN", secret)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_BROAD_LOGIN_SECRET")
    calls = {"n": 0}

    def forbid(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("live fetch")

    monkeypatch.setattr("foreshadow.growth_intel.owner_traffic.fetch_json", forbid)
    runner = CliRunner()
    database = tmp_path / "backdate.sqlite3"
    rejected = runner.invoke(
        app,
        [
            "growth",
            "observe",
            "rainhuang0220/whereToken",
            "--as-of",
            "2020-01-01T00:00:00Z",
            "--database",
            str(database),
        ],
    )
    assert rejected.exit_code != 0
    assert calls["n"] == 0
    assert not database.exists()
    assert secret not in (rejected.stdout + rejected.stderr)
    assert "ghp_BROAD_LOGIN_SECRET" not in (rejected.stdout + rejected.stderr)
    help_text = runner.invoke(app, ["growth", "observe", "--help"])
    assert help_text.exit_code == 0
    assert "--as-of" not in help_text.stdout
    plan_help = runner.invoke(app, ["growth", "plan", "--help"])
    assert "--as-of" in plan_help.stdout

    fixed = datetime(2026, 10, 4, 16, 0, tzinfo=UTC)
    monkeypatch.setattr("foreshadow.growth_intel.owner_traffic.utc_now", lambda: fixed)

    def fake_fetch(identity, kind, *, token, opener=None, allowed=None):
        calls["n"] += 1
        assert token == secret
        assert "ghp_BROAD_LOGIN_SECRET" not in token
        if kind == "views":
            return {
                "count": 1,
                "uniques": 1,
                "views": [{"timestamp": "2026-10-04T00:00:00Z", "count": 1, "uniques": 1}],
            }
        if kind == "clones":
            return {"count": 0, "uniques": 0, "clones": []}
        if kind == "referrers":
            return [{"referrer": "A", "count": 2, "uniques": 1}]
        if kind == "paths":
            return [{"path": "/readme", "count": 1, "uniques": 1}]
        raise AssertionError(kind)

    monkeypatch.setattr("foreshadow.growth_intel.owner_traffic.fetch_json", fake_fetch)
    live = tmp_path / "clock.sqlite3"
    recorded = runner.invoke(
        app,
        ["growth", "observe", "rainhuang0220/whereToken", "--database", str(live)],
    )
    assert recorded.exit_code == 0, recorded.stderr
    assert secret not in (recorded.stdout + recorded.stderr)
    assert "ghp_BROAD_LOGIN_SECRET" not in (recorded.stdout + recorded.stderr)
    conn = connect(live)
    referrers = conn.execute(
        """
        SELECT observed_on, fetched_at, metric, value, grain
        FROM owner_traffic_observations WHERE source='referrers'
        """
    ).fetchall()
    assert referrers
    assert {row[0] for row in referrers} == {"2026-10-04"}
    assert {row[1] for row in referrers} == {"2026-10-04T16:00:00Z"}
    assert {row[4] for row in referrers} == {"window"}
    blob = live.read_bytes()
    assert secret.encode() not in blob
    assert b"ghp_BROAD_LOGIN_SECRET" not in blob


def test_observe_refuses_without_the_owner_token(monkeypatch):
    from typer.testing import CliRunner

    from foreshadow.cli import app

    monkeypatch.delenv("FORESHADOW_OWNER_TRAFFIC_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_BROAD_LOGIN_SECRET")
    result = CliRunner().invoke(app, ["growth", "observe", "acme/tool"])
    assert result.exit_code == 2
    assert "FORESHADOW_OWNER_TRAFFIC_TOKEN" in result.stderr
    assert "Administration" in result.stderr
    assert "ghp_BROAD_LOGIN_SECRET" not in (result.stdout + result.stderr)
    assert "sqlite" not in result.stderr.lower()
