from copy import deepcopy

from foreshadow.config import LLMSettings, Settings
from foreshadow.llm import _SYSTEM, complete, fill_why_now
from foreshadow.models import ComponentScore, ScoreBreakdown
from foreshadow.pipeline.report import build_card
from foreshadow.pipeline.score import ScoredRepo, score_repo
from foreshadow.pipeline.select import select_top


def _llm_on(**over) -> Settings:
    llm = {"enabled": True, "model": "test-model", **over}
    return Settings.model_validate({"llm": llm})


def test_llm_raise_leaves_scores_identical(monkeypatch, frozen_clock, repo_fixture):
    memkit = repo_fixture("memkit.json")
    before = score_repo(memkit, clock=frozen_clock)
    selected = select_top([before])
    snapshot = deepcopy(selected[0].breakdown.model_dump())
    calls: list[int] = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("nope")

    monkeypatch.setattr("foreshadow.llm.complete", boom)
    settings_llm_on = _llm_on()
    after = fill_why_now(selected, settings_llm_on)
    assert calls == [1]
    assert after[0].breakdown.opportunity.value == before.breakdown.opportunity.value
    assert after[0].breakdown.selected_rank == selected[0].breakdown.selected_rank
    assert after[0].breakdown.model_dump() == snapshot
    assert after[0].breakdown.vetoed == before.breakdown.vetoed
    assert after[0].breakdown.veto_reason == before.breakdown.veto_reason
    assert after[0].why_now is None


def test_llm_default_disabled_skips_complete(monkeypatch, frozen_clock, repo_fixture):
    calls: list[int] = []
    monkeypatch.setattr(
        "foreshadow.llm.complete",
        lambda *a, **k: calls.append(1) or "should not run",
    )
    scored = score_repo(repo_fixture("memkit.json"), clock=frozen_clock)
    selected = select_top([scored])
    assert Settings().llm.enabled is False
    after = fill_why_now(selected, Settings())
    assert calls == []
    assert after[0].breakdown.opportunity.value == scored.breakdown.opportunity.value
    assert after[0].why_now is None


def test_llm_success_leaves_scores_identical(monkeypatch, frozen_clock, repo_fixture):
    scored = score_repo(repo_fixture("memkit.json"), clock=frozen_clock)
    selected = select_top([scored])
    snapshot = deepcopy(selected[0].breakdown.model_dump())
    monkeypatch.setattr(
        "foreshadow.llm.complete",
        lambda *a, **k: (
            '{"why_now": "Stars jumped on a small base this week.",'
            ' "contribution": ["Document eviction"]}'
        ),
    )
    after = fill_why_now(selected, _llm_on())
    assert after[0].breakdown.model_dump() == snapshot
    assert after[0].breakdown.selected_rank == 1
    assert after[0].why_now == "Stars jumped on a small base this week."
    assert after[0].contribution_bullets == ["Document eviction"]


def test_complete_posts_chat_completions(respx_mock, monkeypatch):
    import json

    import httpx

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-secret")
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )
    )
    text = complete(
        LLMSettings(enabled=True, model="gpt-4o-mini"),
        [{"role": "user", "content": '{"full_name":"acme/memkit"}'}],
    )
    assert text == "ok"
    assert route.called
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.headers["Authorization"] == "Bearer sk-test-not-a-real-secret"
    body = json.loads(request.content)
    assert body["model"] == "gpt-4o-mini"
    assert body["temperature"] == 0
    assert body["messages"][0]["role"] == "user"


def test_fill_why_now_caps_at_five(monkeypatch):
    calls: list[str] = []

    def fake_complete(llm, messages, **k):
        user = messages[-1]["content"]
        calls.append(user)
        return '{"why_now": "ok", "contribution": []}'

    monkeypatch.setattr("foreshadow.llm.complete", fake_complete)
    cards = [_eligible_card(f"r{i}") for i in range(6)]
    after = fill_why_now(cards, _llm_on())
    assert len(calls) == 5
    assert len(after) == 6
    assert after[5].why_now is None
    for blob in calls:
        assert "acme/r5" not in blob
        assert '"full_name"' in blob


def test_build_card_uses_llm_why_now(frozen_clock, repo_fixture):
    repo = repo_fixture("memkit.json")
    scored = score_repo(repo, clock=frozen_clock)
    scored.why_now = "LLM why now."
    scored.contribution_bullets = ["Fix docs"]
    card = build_card(scored, rank=1, repo=repo)
    assert card["why_now"] == "LLM why now."
    assert card["best_contribution"] == ["Fix docs"]


def test_llm_prompt_forbids_pr_as_first_action():
    blob = _SYSTEM.lower()
    assert "open a pr" in blob
    assert "contributing.md" in blob
    assert "do not tell the user" in blob


def _eligible_card(name: str) -> ScoredRepo:
    hi = ComponentScore(value=80, confidence="high")
    return ScoredRepo(
        owner="acme",
        full_name=f"acme/{name}",
        breakdown=ScoreBreakdown(
            opportunity=ComponentScore(value=90, confidence="high"),
            explosion=hi,
            contribution=hi,
            momentum=ComponentScore(value=90, confidence="high"),
            real_user=hi,
            gap=hi,
            contribution_opp=hi,
            early_entry=hi,
            direction_fit=hi,
            maintainer=hi,
        ),
    )
