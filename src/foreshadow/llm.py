"""Optional LLM Why-now narrative. Default off. Never scores."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from foreshadow.config import LLMSettings, Settings
from foreshadow.pipeline.score import ScoredRepo

log = logging.getLogger("foreshadow.llm")

_FORBIDDEN = ("will explode", "next langchain", "guaranteed")
_DEFAULT_BASE = {
    "openai": "https://api.openai.com/v1",
    "xai": "https://api.x.ai/v1",
    "anthropic": "https://api.anthropic.com/v1",
}
_DEFAULT_MODEL = {
    "openai": "gpt-4o-mini",
    "xai": "grok-3-mini",
    "anthropic": "claude-3-5-haiku-latest",
}
_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "custom": "OPENAI_API_KEY",
}
_SYSTEM = (
    "Write Why-now (2-3 sentences) and at most 3 contribution bullets for one "
    "GitHub repo card. Reply with JSON only: "
    '{"why_now":"...","contribution":["..."]}. '
    "Do not change scores. Never say will explode, next LangChain, or guaranteed. "
    "Explosion is a rule on relative growth, not a forecast. "
    "Do not tell the user to open a PR, add CONTRIBUTING.md, or add CI as the first action."
)


def fill_why_now(
    cards: Sequence[ScoredRepo],
    settings: Settings | LLMSettings,
    *,
    repos: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[ScoredRepo]:
    """Fill Why-now on selected cards. Does not mutate scores, vetoes, or rank."""
    out = list(cards)
    llm = _llm_of(settings)
    if repos:
        for card in out:
            _bind_repo(card, repos.get(card.full_name))
    if not llm.enabled:
        return out
    try:
        cap = int(llm.max_calls_per_run)
    except (TypeError, ValueError):
        cap = 5
    cap = max(0, min(cap, 5, len(out)))
    for card in out[:cap]:
        try:
            content = complete(llm, _messages(card))
        except RuntimeError as exc:
            log.debug("LLM narrative skipped (%s)", type(exc).__name__)
            continue
        why, bullets = _parse(content)
        if why:
            card.why_now = why
        if bullets:
            card.contribution_bullets = bullets[:3]
    return out


def complete(
    llm: LLMSettings,
    messages: Sequence[Mapping[str, str]],
    *,
    timeout: float = 30.0,
) -> str:
    try:
        return _post_completion(llm, messages, timeout=timeout)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("LLM request failed") from exc


def _post_completion(
    llm: LLMSettings,
    messages: Sequence[Mapping[str, str]],
    *,
    timeout: float,
) -> str:
    key = _api_key(llm.provider)
    provider = (llm.provider or "openai").lower()
    model = (llm.model or "").strip() or _DEFAULT_MODEL.get(provider, "")
    if not model:
        raise RuntimeError("missing LLM model")
    url = _completions_url(_base_url(llm))
    payload = {
        "model": model,
        "messages": [dict(item) for item in messages],
        "temperature": 0,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(f"LLM HTTP {resp.status_code}")
    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM invalid JSON") from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("LLM empty completion") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM empty completion")
    return content


def _llm_of(settings: Settings | LLMSettings) -> LLMSettings:
    if isinstance(settings, LLMSettings):
        return settings
    return settings.llm


def _api_key(provider: str) -> str:
    name = _KEY_ENV.get((provider or "openai").lower(), "OPENAI_API_KEY")
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing {name}")
    return value


def _base_url(llm: LLMSettings) -> str:
    custom = (llm.base_url or "").strip().rstrip("/")
    if custom:
        return custom
    provider = (llm.provider or "openai").lower()
    url = _DEFAULT_BASE.get(provider, _DEFAULT_BASE["openai"])
    if not url:
        raise RuntimeError("missing LLM base_url")
    return url


def _completions_url(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _bind_repo(card: ScoredRepo, repo: Mapping[str, Any] | None) -> None:
    repo = repo or {}
    feat = repo.get("features")
    if not isinstance(feat, Mapping):
        feat = {}
    titles: list[str] = []
    for key in ("open_issue_titles", "help_issue_titles"):
        for title in feat.get(key) or []:
            text = str(title).strip()
            if text and text not in titles:
                titles.append(text)
            if len(titles) == 5:
                break
        if len(titles) == 5:
            break
    ev = card.evidence
    ev.setdefault("description", str(repo.get("description") or ""))
    ev.setdefault("issue_titles", titles)


def _messages(card: ScoredRepo) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _card_json(card)},
    ]


def _card_json(card: ScoredRepo) -> str:
    bd = card.breakdown
    ev = card.evidence or {}
    titles = [str(t) for t in list(ev.get("issue_titles") or [])[:5]]
    payload = {
        "full_name": card.full_name,
        "description": str(ev.get("description") or ""),
        "scores": {
            "opportunity": bd.opportunity.value,
            "explosion": bd.explosion.value,
            "contribution": bd.contribution.value,
            "momentum": bd.momentum.value,
            "real_user": bd.real_user.value,
            "gap": bd.gap.value,
            "contribution_opp": bd.contribution_opp.value,
            "early_entry": bd.early_entry.value,
            "direction_fit": bd.direction_fit.value,
            "maintainer": bd.maintainer.value,
        },
        "issue_titles": titles,
    }
    return json.dumps(payload, ensure_ascii=False)


def _parse(text: str) -> tuple[str | None, list[str]]:
    raw = (text or "").strip()
    if not raw:
        return None, []
    data = _coerce_json(raw)
    why = ""
    bullets: list[str] = []
    if isinstance(data, dict):
        why = str(data.get("why_now") or data.get("why") or "").strip()
        extra = data.get("contribution") or data.get("bullets") or []
        if isinstance(extra, str):
            extra = [extra]
        if isinstance(extra, list):
            bullets = [str(item).strip() for item in extra if str(item).strip()][:3]
    else:
        why = raw
    if why and _forbidden(why):
        why = ""
    bullets = [item for item in bullets if not _forbidden(item)][:3]
    return (why or None), bullets


def _forbidden(text: str) -> bool:
    low = text.lower()
    return any(phrase in low for phrase in _FORBIDDEN)


def _coerce_json(text: str) -> Any:
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", stripped)
    if fence:
        stripped = fence.group(1).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None
