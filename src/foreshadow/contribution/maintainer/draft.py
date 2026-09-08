"""Compose a short maintainer-facing PR from the safe context only."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from foreshadow.contribution.maintainer.context import MaintainerDraftContext
from foreshadow.contribution.maintainer.gate import (
    GateResult,
    evaluate_maintainer_output,
)

_DROP_LINE = re.compile(
    r"ignore previous|github_token|ghp_[a-z0-9]|gho_[a-z0-9]|<script|"
    r"/etc/foreshadow|openai_api_key|anthropic_api_key",
    re.IGNORECASE,
)
_HTML = re.compile(r"<[^>]+>")
_ADDED = re.compile(r"^\+[^+].+", re.MULTILINE)
_TEST_FUNC = re.compile(r"^\+func (Test\w+)", re.MULTILINE)


@dataclass(frozen=True)
class MaintainerDraft:
    title: str
    body: str


def _clean_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in (text or "").splitlines():
        if _DROP_LINE.search(raw):
            continue
        line = _HTML.sub("", raw).strip()
        if line:
            out.append(line)
    return out


def _first_sentence(text: str) -> str:
    blob = " ".join(_clean_lines(text))
    if not blob:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", blob, maxsplit=1)
    sentence = parts[0].strip()
    return sentence[:280]


def _scope(files: list[str]) -> str:
    blob = " ".join(files).lower()
    if "friction" in blob:
        return "friction"
    if "doctor" in blob:
        return "doctor"
    if "/sources/" in blob or "sources" in blob:
        return "sources"
    if files:
        parent = Path(files[0]).parent.name
        if parent and parent not in {".", ""}:
            return parent[:24]
        return Path(files[0]).stem[:24]
    return "core"


def _is_friction(ctx: MaintainerDraftContext) -> bool:
    return any("friction" in path.lower() for path in ctx.changed_files)


def _title_summary(ctx: MaintainerDraftContext) -> str:
    added = _added_phrases(ctx.diff)
    if _is_friction(ctx) and added:
        token = added[0].strip().strip("\"'`")
        return f"treat {token} as friction"
    nothing = re.search(
        r"says nothing about (.+)$", ctx.issue_title or "", re.IGNORECASE
    )
    if nothing:
        return nothing.group(1).strip().rstrip(".")
    raw = (ctx.issue_title or _first_sentence(ctx.issue_body) or "contribution").strip()
    raw = raw.replace('"', "").replace("'", "")
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = re.split(r",\s+so\s+", raw, maxsplit=1)[0]
    if len(raw) > 68:
        raw = raw[:65].rstrip() + "..."
    if raw and raw[0].isupper():
        raw = raw[0].lower() + raw[1:]
    return raw or "contribution"


def _added_phrases(diff: str) -> list[str]:
    found: list[str] = []
    for match in _ADDED.finditer(diff or ""):
        line = match.group(0)[1:].strip()
        line = line.strip('`",')
        if 2 < len(line) < 80 and not line.startswith("package "):
            found.append(line)
        if len(found) >= 4:
            break
    return found


def _behavior_sentence(ctx: MaintainerDraftContext) -> str:
    added = _added_phrases(ctx.diff)
    names = [Path(p).name for p in ctx.changed_files[:3]]
    if added and _is_friction(ctx):
        sample = ", ".join(f"`{p}`" for p in added[:3])
        return f"Linker messages such as {sample} now count as friction."
    if added and names:
        sample = ", ".join(f"`{p}`" for p in added[:2])
        return f"{', '.join(names)} now covers {sample}."
    if names:
        return f"Update {', '.join(names)}."
    return "Apply the attached patch."


def compose_maintainer_draft(ctx: MaintainerDraftContext) -> MaintainerDraft:
    """Deterministic draft. Never reads entry why, scores, or task extras."""
    scope = _scope(ctx.changed_files)
    title = f"fix({scope}): {_title_summary(ctx)}"[:120]
    behavior = _behavior_sentence(ctx)
    lines: list[str] = []
    if ctx.issue_number is not None:
        lines.append(f"Closes #{ctx.issue_number}.")
        lines.append("")
    lines.append(behavior)
    tests = _TEST_FUNC.findall(ctx.diff or "")
    if tests:
        lines.append("")
        lines.append(f"Fail-before: `{tests[0]}`.")
    body = "\n".join(lines).strip() + "\n"
    return MaintainerDraft(title=title, body=body)


def compose_and_gate(
    ctx: MaintainerDraftContext,
    *,
    semantic_reviewer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    max_attempts: int = 3,
) -> tuple[MaintainerDraft, GateResult]:
    last: tuple[MaintainerDraft, GateResult] | None = None
    for _ in range(max(1, int(max_attempts))):
        draft = compose_maintainer_draft(ctx)
        gate = evaluate_maintainer_output(
            draft.title,
            draft.body,
            ctx,
            semantic_reviewer=semantic_reviewer,
        )
        last = (draft, gate)
        if gate.ok:
            return last
    assert last is not None
    return last
