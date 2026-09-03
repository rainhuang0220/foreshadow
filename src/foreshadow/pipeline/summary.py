"""Extractive project summary. Never invent positioning not in the sources."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

INSUFFICIENT = "信息不足，无法写简介。"
MISSING = INSUFFICIENT
_MAX_CHARS = 500
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HTML_TAG = re.compile(r"</?[^>]+>")
_BADGE = re.compile(r"(?i)(build status|coverage|license|pypi version|npm version)")
_INSTALL_LINE = re.compile(
    r"(?i)^(pip|pipx|npm|pnpm|yarn|cargo|go|gem|brew)\s+(install|add|get)\b"
)


@dataclass
class ProjectSummary:
    text: str
    source: str
    source_sha: str | None = None
    at: str | None = None

    @property
    def summary(self) -> str:
        return self.text

    @property
    def summary_at(self) -> str | None:
        return self.at

    @property
    def summary_source_sha(self) -> str | None:
        return self.source_sha


def should_refresh(stored_sha: str | None, current_sha: str | None) -> bool:
    stored = (stored_sha or "").strip()
    if not stored:
        return True
    current = (current_sha or "").strip()
    if not current:
        return True
    return stored != current


def summarize_project(
    description: str | None = None,
    readme: str | None = None,
    topics: Sequence[str] | None = None,
    source_sha: str | None = None,
    **kwargs: Any,
) -> ProjectSummary:
    description = description if description is not None else kwargs.get("description")
    readme = readme if readme is not None else kwargs.get("readme")
    topics = topics if topics is not None else kwargs.get("topics")
    source_sha = source_sha if source_sha is not None else kwargs.get("source_sha")
    now = datetime.now(UTC).isoformat()
    lines: list[str] = []
    source = "limited"
    desc = _clean(description)
    if desc:
        lines.append(desc)
        source = "github"
    para = first_readme_paragraph(readme)
    if para and (not desc or para.lower() not in desc.lower()):
        lines.append(para)
        if source == "limited":
            source = "readme"
    topic_line = _topics_line(topics)
    if topic_line:
        lines.append(topic_line)
    if not lines:
        return ProjectSummary(
            text=INSUFFICIENT, source="limited", source_sha=source_sha, at=now
        )
    return ProjectSummary(
        text=_clip("\n".join(lines[:4])),
        source=source,
        source_sha=source_sha,
        at=now,
    )


def maybe_llm_summary(
    extractive: ProjectSummary | dict[str, Any],
    *,
    llm_enabled: bool = False,
    complete_fn: Any = None,
    settings: Any = None,
    description: str | None = None,
    **_kwargs: Any,
) -> ProjectSummary | dict[str, Any]:
    if not llm_enabled:
        return extractive
    if isinstance(extractive, ProjectSummary):
        body = extractive.text
    else:
        body = str(extractive.get("summary") or extractive.get("text") or "")
    if not body or body == INSUFFICIENT:
        return extractive
    user = body if not description else f"{description}\n{body}"
    messages = [
        {
            "role": "system",
            "content": "Only use provided text. Do not invent positioning.",
        },
        {"role": "user", "content": user},
    ]
    try:
        if complete_fn is not None:
            text = complete_fn(settings, messages)
        else:
            from foreshadow.llm import complete

            text = complete(settings, messages)
    except (RuntimeError, TypeError, ValueError, OSError, KeyError):
        return extractive
    cleaned = _clean(text if isinstance(text, str) else str(text or ""))
    if not cleaned:
        return extractive
    if isinstance(extractive, ProjectSummary):
        return ProjectSummary(
            text=_clip(cleaned),
            source=extractive.source,
            source_sha=extractive.source_sha,
            at=extractive.at,
        )
    out = dict(extractive)
    out["summary"] = _clip(cleaned)
    out["text"] = out["summary"]
    return out


def first_readme_paragraph(raw: str | None) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    in_fence = False
    buf: list[str] = []
    paragraphs: list[str] = []

    def flush() -> None:
        if buf:
            paragraphs.append(" ".join(buf))
            buf.clear()

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            flush()
            continue
        if stripped.startswith("#"):
            flush()
            continue
        if stripped in {"---", "***", "___"}:
            continue
        if stripped.startswith(("<!--", "|")):
            continue
        if stripped.startswith(("![", "<img")):
            continue
        if _BADGE.search(stripped) and len(stripped) < 120:
            continue
        if _INSTALL_LINE.search(stripped) and len(stripped) < 80:
            continue
        buf.append(stripped)
        if sum(len(x) for x in buf) > 280:
            flush()
            break
    flush()
    for para in paragraphs:
        cleaned = _clean(para)
        if cleaned and len(cleaned) >= 24:
            return cleaned
    return None


def _topics_line(topics: Sequence[str] | None) -> str | None:
    if not topics:
        return None
    names = [str(t).strip() for t in topics if str(t).strip()][:8]
    if not names:
        return None
    return "主题：" + ", ".join(names)


def _clean(value: str | None) -> str:
    if not value:
        return ""
    text = _MD_IMAGE.sub("", value)
    text = _MD_LINK.sub(r"\1", text)
    text = _HTML_TAG.sub("", text)
    text = " ".join(text.split())
    return text.strip()


def _clip(text: str) -> str:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()][:4]
    joined = "\n".join(lines)
    if len(joined) <= _MAX_CHARS:
        return joined
    return joined[: _MAX_CHARS - 1].rstrip() + "…"
