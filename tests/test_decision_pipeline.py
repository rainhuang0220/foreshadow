from datetime import UTC, datetime, timedelta

import pytest

NOW = datetime(2026, 10, 3, tzinfo=UTC)


def candidate():
    from foreshadow.decision.models import (
        Evidence,
        Observation,
        Opportunity,
        Repository,
        Validation,
    )
    from foreshadow.decision.task import StructuredTask

    repository = Repository(
        identity="acme/project", path="/tmp/project", base_revision="a" * 40
    )
    obs = Observation(
        id="obs-1",
        repository_identity="acme/project",
        observed_at=NOW,
        source="git:" + "a" * 40 + ":src/parser.py",
        summary="Parser has no type guard",
    )
    evidence = Evidence.observed(obs, expires_at=NOW + timedelta(days=3))
    task = StructuredTask(
        repository="acme/project",
        task="Guard parser",
        expected_behavior="Reject lists",
        acceptance_criteria=["List input returns a structured error"],
    )
    opportunity = Opportunity(
        id="opportunity-1",
        repository=repository,
        title="Guard parser",
        objective="Reject list input before accessing keys",
        rationale="List input crashes",
        task=task,
        evidence=(evidence,),
        confidence=0.8,
        validation=(
            Validation(
                argv=("python3", "-m", "unittest"),
                expectation="Tests pass",
                timeout_seconds=60,
            ),
        ),
    )
    return opportunity, obs


def test_validated_opportunity_exports_without_private_scores():
    from foreshadow.decision.pipeline import export_work_order, validate_opportunity
    from foreshadow.work_order import dumps

    opportunity, obs = candidate()
    valid = validate_opportunity(opportunity, (obs,), now=NOW)
    order = export_work_order(valid, now=NOW)
    assert order["repository"]["base_revision"] == "a" * 40
    assert order["objective"] == "Reject list input before accessing keys"
    assert order["evidence"][0]["observed_at"] == "2026-10-03T00:00:00Z"
    assert "confidence" not in dumps(order)
    assert order["provenance"]["evidence_ids"] == ["obs-1"]
    assert dumps(order) == dumps(export_work_order(valid, now=NOW))


def test_validated_task_snapshot_cannot_change_when_candidate_is_mutated():
    from foreshadow.decision.pipeline import export_work_order, validate_opportunity
    from foreshadow.work_order import dumps

    opportunity, obs = candidate()
    valid = validate_opportunity(opportunity, (obs,), now=NOW)
    before = dumps(export_work_order(valid, now=NOW))
    opportunity.task.constraints.append("Silently expand the scope")
    opportunity.task.acceptance_criteria.clear()
    assert dumps(export_work_order(valid, now=NOW)) == before
    with pytest.raises((AttributeError, TypeError)):
        valid.opportunity.task.constraints += ("Another mutation",)


@pytest.mark.parametrize("confidence", [True, float("nan"), float("inf"), "high"])
def test_invalid_confidence_is_a_structured_rejection(confidence):
    from dataclasses import replace

    from foreshadow.decision.pipeline import validate_opportunity

    opportunity, obs = candidate()
    with pytest.raises(ValueError, match="actionable"):
        validate_opportunity(
            replace(opportunity, confidence=confidence), (obs,), now=NOW
        )


def test_candidate_cannot_export_without_validation():
    from foreshadow.decision.pipeline import export_work_order

    opportunity, _ = candidate()
    with pytest.raises(ValueError, match="validated"):
        export_work_order(opportunity, now=NOW)


def test_expired_future_missing_and_wrong_repository_observations_are_rejected():
    from dataclasses import replace

    from foreshadow.decision.pipeline import validate_opportunity

    opportunity, obs = candidate()
    cases = [
        (opportunity, ()),
        (opportunity, (replace(obs, repository_identity="other/repo"),)),
        (opportunity, (replace(obs, observed_at=NOW + timedelta(seconds=1)),)),
        (
            replace(
                opportunity,
                evidence=(replace(opportunity.evidence[0], expires_at=NOW),),
            ),
            (obs,),
        ),
    ]
    for item, observations in cases:
        with pytest.raises(ValueError):
            validate_opportunity(item, observations, now=NOW)
    valid = validate_opportunity(opportunity, (obs,), now=NOW)
    from foreshadow.decision.pipeline import export_work_order

    with pytest.raises(ValueError, match="stale"):
        export_work_order(valid, now=NOW + timedelta(days=4))


def test_inference_keeps_lineage_and_never_acquires_an_observation_timestamp():
    from dataclasses import replace

    from foreshadow.decision.models import Evidence
    from foreshadow.decision.pipeline import export_work_order, validate_opportunity

    opportunity, obs = candidate()
    inference = Evidence.inferred(
        id="inference-1",
        summary="A type guard is a bounded fix",
        source="decision:manual-review",
        observations=(obs,),
        expires_at=NOW + timedelta(days=3),
    )
    opportunity = replace(opportunity, evidence=opportunity.evidence + (inference,))
    exported = export_work_order(
        validate_opportunity(opportunity, (obs,), now=NOW), now=NOW
    )
    inferred = next(e for e in exported["evidence"] if e["kind"] == "inference")
    assert inferred["observed_at"] is None
    assert inferred["observation_ids"] == ["obs-1"]


def test_actionability_and_ranking_have_deterministic_ties():
    from dataclasses import replace

    from foreshadow.decision.pipeline import rank_opportunities, validate_opportunity

    opportunity, obs = candidate()
    for item in (
        replace(opportunity, objective=""),
        replace(opportunity, validation=()),
        replace(opportunity, confidence=0.2),
    ):
        with pytest.raises(ValueError):
            validate_opportunity(item, (obs,), now=NOW)
    a = validate_opportunity(replace(opportunity, id="a"), (obs,), now=NOW)
    b = validate_opportunity(replace(opportunity, id="b"), (obs,), now=NOW)
    assert [x.opportunity.id for x in rank_opportunities([b, a])] == ["a", "b"]
    assert [x.opportunity.id for x in rank_opportunities([a, b])] == ["a", "b"]


def test_task_compatibility_import_preserves_existing_api():
    from foreshadow.contribution.task import StructuredTask as LegacyTask
    from foreshadow.decision.task import StructuredTask

    assert StructuredTask is LegacyTask
