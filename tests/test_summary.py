from foreshadow.config import LLMSettings
from foreshadow.pipeline.summary import (
    INSUFFICIENT,
    maybe_llm_summary,
    should_refresh,
    summarize_project,
)
from foreshadow.pipeline.thesis import MISSING, extract_thesis

LONG_README = (
    "# memkit\n\n"
    "This library stores embeddings on disk for local RAG agents that need "
    "a small memory layer without a hosted database.\n\n"
    "## Install\n\n"
    "pip install memkit\n\n"
    "## More\n\n" + ("UNIQUE_TAIL_PARAGRAPH_SHOULD_NOT_APPEAR in the summary. " * 40)
)


def test_description_only():
    summary = summarize_project(
        description="Local RAG memory for LLM agents",
        readme=None,
        topics=None,
        source_sha="abc",
    )
    assert summary.source == "github"
    assert summary.source_sha == "abc"
    assert summary.text == "Local RAG memory for LLM agents"
    assert "主题：" not in summary.text


def test_readme_paragraph():
    readme = (
        "# memkit\n\n"
        "![ci](https://img.shields.io/badge/ci-passing-green)\n\n"
        "[![Build Status](https://travis-ci.org/acme/memkit.svg)]"
        "(https://travis-ci.org/acme/memkit)\n\n"
        "A tiny local-first memory layer for RAG pipelines.\n\n"
        "## Install\n\n"
        "pip install memkit\n"
    )
    summary = summarize_project(
        description=None,
        readme=readme,
        topics=["rag", "memory"],
        source_sha="sha1",
    )
    assert summary.source == "readme"
    assert "tiny local-first memory layer" in summary.text
    assert "主题：rag, memory" in summary.text.splitlines()[-1]
    assert "pip install" not in summary.text
    assert "Build Status" not in summary.text
    assert "img.shields.io" not in summary.text


def test_empty_is_limited():
    summary = summarize_project(
        description=None, readme=None, topics=None, source_sha=None
    )
    assert summary.text == INSUFFICIENT
    assert summary.text == "信息不足，无法写简介。"
    assert summary.source == "limited"


def test_does_not_copy_entire_readme():
    summary = summarize_project(
        description=None, readme=LONG_README, topics=None, source_sha="1"
    )
    assert summary.source == "readme"
    assert "stores embeddings on disk" in summary.text
    assert "UNIQUE_TAIL_PARAGRAPH_SHOULD_NOT_APPEAR" not in summary.text
    assert len(summary.text) <= 500
    assert summary.text != LONG_README


def test_does_not_invent_competitors():
    thesis = extract_thesis(
        description="A local memory kit",
        readme="# memkit\n\nA tiny memory layer for agents.\n",
        headings=["Install", "Usage"],
        topics=["rag"],
        releases_30d=1,
        age_days=40,
    )
    assert thesis["main_competitors"] == MISSING
    assert thesis["main_competitors"] == "信息不足"
    assert "LangChain" not in thesis["main_competitors"]
    assert thesis["current_maturity"] == "约 40 天，近 30 天有 release"


def test_should_refresh_on_sha_change():
    assert should_refresh(None, "abc") is True
    assert should_refresh("", "abc") is True
    assert should_refresh("   ", "abc") is True
    assert should_refresh("abc", "abc") is False
    assert should_refresh("abc", "def") is True
    assert should_refresh("abc", None) is True


def test_prefers_github_description_as_line1():
    summary = summarize_project(
        description="GitHub desc here for the product.",
        readme="# t\n\nA longer README paragraph about the same product for developers.\n",
        topics=["rag"],
        source_sha="sha",
    )
    assert summary.source == "github"
    assert summary.text.splitlines()[0] == "GitHub desc here for the product."
    assert "主题：rag" in summary.text


def test_strips_markdown_links():
    summary = summarize_project(
        description="See [Memkit](https://example.com) on disk for agents.",
        readme=None,
        topics=None,
        source_sha="s",
    )
    assert "https://example.com" not in summary.text
    assert "Memkit" in summary.text


def test_badge_and_install_only_readme_is_limited():
    readme = (
        "# memkit\n\n"
        "<img src='https://img.shields.io/badge/ci-passing-green'>\n\n"
        "pip install memkit\n"
    )
    summary = summarize_project(
        description="  ", readme=readme, topics=None, source_sha="x"
    )
    assert summary.source == "limited"
    assert summary.text == INSUFFICIENT


def test_thesis_empty_is_insufficient():
    thesis = extract_thesis(
        description=None,
        readme=None,
        headings=None,
        topics=None,
        releases_30d=None,
        age_days=None,
    )
    assert thesis["what"] == MISSING
    assert thesis["why_it_may_matter"] == MISSING
    assert thesis["target_users"] == MISSING
    assert thesis["technical_differentiation"] == MISSING
    assert thesis["current_maturity"] == MISSING
    assert thesis["main_competitors"] == MISSING
    assert thesis["risks"] == MISSING


def test_thesis_maturity_without_release_is_not_zero_filled():
    thesis = extract_thesis(
        description="A kit",
        readme=None,
        headings=None,
        topics=None,
        releases_30d=None,
        age_days=12,
    )
    assert thesis["current_maturity"] == "约 12 天"
    none_rel = extract_thesis(
        description="A kit",
        readme=None,
        headings=None,
        topics=None,
        releases_30d=0,
        age_days=12,
    )
    assert none_rel["current_maturity"] == "约 12 天，近 30 天无 release"


def test_thesis_extracts_named_alternatives():
    thesis = extract_thesis(
        description="A memory kit",
        readme="# x\n\nA kit.\n\n## Alternatives\n\n- LangChain\n- LlamaIndex\n",
        headings=["Alternatives"],
        topics=None,
        releases_30d=None,
        age_days=None,
    )
    assert "LangChain" in thesis["main_competitors"]
    assert thesis["main_competitors"] != MISSING


def test_maybe_llm_summary_noop_when_disabled(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(
        "foreshadow.llm.complete",
        lambda *a, **k: calls.append(1) or "should not run",
    )
    base = summarize_project(
        description="A local RAG memory kit for agents.",
        readme=None,
        topics=None,
        source_sha="s",
    )
    out = maybe_llm_summary(
        base,
        description="A local RAG memory kit for agents.",
        llm_enabled=False,
    )
    assert calls == []
    assert out.text == base.text


def test_maybe_llm_keeps_extractive_on_failure(monkeypatch):
    monkeypatch.setattr(
        "foreshadow.llm.complete",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope")),
    )
    base = summarize_project(
        description="A local RAG memory kit for agents.",
        readme=None,
        topics=None,
        source_sha="s",
    )
    out = maybe_llm_summary(
        base,
        description="A local RAG memory kit for agents.",
        llm_enabled=True,
        settings=LLMSettings(enabled=True, model="test-model"),
    )
    assert out.text == base.text


def test_maybe_llm_prompt_forbids_invention(monkeypatch):
    captured: list[list[dict[str, str]]] = []

    def fake_complete(llm, messages, **k):
        captured.append(list(messages))
        return "A local RAG memory kit for agents."

    monkeypatch.setattr("foreshadow.llm.complete", fake_complete)
    base = summarize_project(
        description="A local RAG memory kit for agents.",
        readme=None,
        topics=None,
        source_sha="s",
    )
    out = maybe_llm_summary(
        base,
        description="A local RAG memory kit for agents.",
        llm_enabled=True,
        settings=LLMSettings(enabled=True, model="test-model"),
    )
    blob = str(captured).lower()
    assert "only use provided text" in blob
    assert "do not invent" in blob
    assert out.source == base.source
    assert len(captured) == 1
