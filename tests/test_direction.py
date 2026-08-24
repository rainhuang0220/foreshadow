from foreshadow.pipeline.direction import (
    is_keyword_stuffing,
    load_direction_bags,
    score_direction,
    stuffing_tokens,
)


def test_rag_memory_topics_at_least_70():
    bags = load_direction_bags()
    n = score_direction(
        name="",
        description="",
        topics=["memory", "rag", "llm"],
        headings=[],
        language="",
        bags=bags,
    )
    assert n >= 70


def test_p7_stuffing_detected():
    assert is_keyword_stuffing("awesome best ultimate AI LLM agent") is True
    assert stuffing_tokens("awesome best ultimate AI LLM agent") >= {
        "ai",
        "llm",
        "agent",
        "awesome",
        "best",
        "ultimate",
    }
    assert is_keyword_stuffing("memory rag llm toolkit") is False


def test_p7_stuffing_is_word_tokens_not_substrings():
    assert is_keyword_stuffing("available intelligent storage") is False
