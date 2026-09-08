"""MAINTAINER_OUTPUT_GATE. Any FAIL blocks third-party GitHub writes."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from foreshadow.contribution.executor import RemoteWriteRefused
from foreshadow.contribution.maintainer.context import MaintainerDraftContext
from foreshadow.contribution.maintainer.lint import (
    ai_attribution_hits,
    cross_issue_hits,
    default_semantic_reasons,
    diff_claim_hits,
    grounding_hits,
    language_hits,
    leak_hits,
    privacy_hits,
    style_hits,
    test_claim_hits,
)

CHECK_NAMES = (
    "internal_leakage",
    "privacy",
    "grounding",
    "cross_issue",
    "language",
    "repo_style",
    "tests_claims",
    "diff_claims",
    "ai_self_reference",
    "semantic_review",
)

_SUMMARY_PASS = (
    "Grounded in issue/diff",
    "Internal metadata clean",
    "Repository style checked",
)


@dataclass
class GateResult:
    ok: bool
    verdict: str
    checks: dict[str, str]
    reasons: list[str] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    blocks_remote: bool = True
    details: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "verdict": self.verdict,
            "checks": dict(self.checks),
            "reasons": list(self.reasons),
            "summary": list(self.summary),
            "blocks_remote": self.blocks_remote,
            "details": list(self.details),
        }


def _status(hits: list[str]) -> str:
    return "FAIL" if hits else "PASS"


def evaluate_maintainer_output(
    title: str,
    body: str,
    context: MaintainerDraftContext,
    *,
    semantic_reviewer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> GateResult:
    text = f"{title}\n{body}"
    hits = {
        "internal_leakage": leak_hits(text, context),
        "privacy": privacy_hits(text, context),
        "grounding": grounding_hits(body, context),
        "cross_issue": cross_issue_hits(text, context),
        "language": language_hits(text, context),
        "repo_style": style_hits(title, body, context),
        "tests_claims": test_claim_hits(body, context),
        "diff_claims": diff_claim_hits(body, context),
        "ai_self_reference": ai_attribution_hits(text, context),
    }
    payload = {
        "issue_title": context.issue_title,
        "issue_body": context.issue_body,
        "diff": context.diff,
        "tests": list(context.test_commands),
        "contributing": context.contributing,
        "pr_template": context.pr_template,
        "recent_pr_titles": list(context.recent_pr_titles),
        "draft": {"title": title, "body": body},
    }
    reviewer = semantic_reviewer or _llm_semantic_reviewer
    review = reviewer(payload) or {}
    semantic_ok = bool(review.get("ok", True))
    semantic_reasons = [str(x) for x in (review.get("reasons") or [])]
    if semantic_reviewer is None and not semantic_reasons:
        semantic_reasons = default_semantic_reasons(f"{title}\n{body}")
        semantic_ok = not semantic_reasons
    hits["semantic_review"] = (
        [] if semantic_ok else (semantic_reasons or ["reviewer-fail"])
    )

    checks = {name: _status(hits.get(name) or []) for name in CHECK_NAMES}
    reasons: list[str] = []
    details: list[dict[str, Any]] = []
    for name in CHECK_NAMES:
        items = hits.get(name) or []
        details.append({"name": name, "status": checks[name], "hits": items})
        reasons.extend(f"{name}: {item}" for item in items)
    ok = all(status == "PASS" for status in checks.values())
    verdict = "MAINTAINER_OUTPUT_SAFE" if ok else "MAINTAINER_OUTPUT_UNSAFE"
    if ok:
        summary = list(_SUMMARY_PASS)
    else:
        summary = ["Unsafe draft — remote submission blocked"]
    return GateResult(
        ok=ok,
        verdict=verdict,
        checks=checks,
        reasons=reasons,
        summary=summary,
        blocks_remote=not ok,
        details=details,
    )


def _builtin_semantic(payload: dict[str, Any]) -> dict[str, Any]:
    draft = payload.get("draft") or {}
    if isinstance(draft, dict):
        text = f"{draft.get('title') or ''}\n{draft.get('body') or ''}"
    else:
        text = str(draft)
    reasons = default_semantic_reasons(text)
    return {"ok": not reasons, "reasons": reasons}


def _llm_semantic_reviewer(payload: dict[str, Any]) -> dict[str, Any]:
    """Optional isolated reviewer. Does not see generator notes. Fail-closed."""
    try:
        from foreshadow.config import load_config
        from foreshadow.llm import complete
    except ImportError:
        return _builtin_semantic(payload)
    settings = load_config()
    llm = getattr(settings, "llm", None)
    if llm is None or not getattr(llm, "enabled", False):
        return _builtin_semantic(payload)
    draft = payload.get("draft") or {}
    messages = [
        {
            "role": "system",
            "content": (
                "You review a pull request that will be sent under a human "
                "contributor's name. Reply JSON only: "
                '{"ok":true|false,"reasons":["..."]}. '
                "Fail if the draft leaks internal tooling, invents claims, "
                "mixes issues, sounds like an agent, or would embarrass the author."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "issue_title": payload.get("issue_title"),
                    "issue_body": payload.get("issue_body"),
                    "diff": payload.get("diff"),
                    "tests": payload.get("tests"),
                    "contributing": payload.get("contributing"),
                    "draft": draft,
                },
                ensure_ascii=False,
            )[:12000],
        },
    ]
    try:
        raw = complete(llm, messages, timeout=20.0)
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"ok": False, "reasons": ["reviewer-invalid"]}
        return {
            "ok": bool(data.get("ok")),
            "reasons": [str(x) for x in (data.get("reasons") or [])],
        }
    except (RuntimeError, json.JSONDecodeError, TypeError, ValueError):
        return {"ok": False, "reasons": ["reviewer-unavailable"]}


def assert_remote_submission_allowed(gate: GateResult) -> None:
    if not gate.ok:
        raise RemoteWriteRefused("MAINTAINER_OUTPUT_UNSAFE")


def prepare_remote_submission(
    conn: sqlite3.Connection,
    user_id: int,
    mission_id: int,
    *,
    action: str,
) -> dict[str, Any]:
    """The only future YOLO entry. Evaluates the current draft and refuses if unsafe."""
    from foreshadow.contribution.review import pr_draft

    draft = pr_draft(conn, user_id, mission_id)
    safety = draft.get("safety") or {}
    gate = GateResult(
        ok=bool(safety.get("ok")),
        verdict=str(safety.get("verdict") or "MAINTAINER_OUTPUT_UNSAFE"),
        checks=dict(safety.get("checks") or {}),
        summary=list(safety.get("summary") or []),
        blocks_remote=not bool(safety.get("ok")),
    )
    assert_remote_submission_allowed(gate)
    return evaluate_remote_submission(action, gate=gate)


def evaluate_remote_submission(
    action: str, *, gate: GateResult | None = None
) -> dict[str, Any]:
    """Future YOLO hook. Unsafe drafts never reach GitHub; safe ones still need approval."""
    if gate is not None and not gate.ok:
        return {
            "ok": False,
            "blocked": True,
            "action": action,
            "status": "MAINTAINER_OUTPUT_UNSAFE",
            "error": "Maintainer-facing draft failed the output safety gate.",
            "remote_writes": 0,
            "gate": gate.as_dict(),
        }
    from foreshadow.mission import refuse_remote_action

    out = dict(refuse_remote_action(action))
    out["remote_writes"] = 0
    return out
