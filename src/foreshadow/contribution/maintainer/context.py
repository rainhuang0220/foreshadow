"""Safe projection from internal contribution state to maintainer-facing inputs."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from foreshadow.contribution.task import StructuredTask

_CJK = re.compile(r"[\u4e00-\u9fff]")
_LEAK_HINT = re.compile(
    r"official\s+top\s*5|人工确认|foreshadow|entry strategy|human[- ]confirm",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MaintainerDraftContext:
    """Only fields a third-party maintainer is allowed to see as sources."""

    repository: str
    issue_number: int | None
    issue_title: str
    issue_body: str
    diff: str
    changed_files: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)
    tests_ok: bool = False
    contributing: str = ""
    pr_template: str = ""
    recent_pr_titles: list[str] = field(default_factory=list)
    language: str = "en"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_maintainer_language(
    *,
    contributing: str = "",
    issue_title: str = "",
    issue_body: str = "",
    recent_pr_titles: list[str] | None = None,
) -> str:
    blob = " ".join([contributing, issue_title, " ".join(recent_pr_titles or [])])
    cjk = len(_CJK.findall(blob))
    latin = sum(1 for ch in blob if ch.isascii() and ch.isalpha())
    if cjk > max(latin, 8):
        return "zh"
    return "en"


def project_maintainer_context(
    *,
    repository: str,
    structured: StructuredTask | None = None,
    diff: str = "",
    files: list[str] | None = None,
    test_commands: list[str] | None = None,
    tests_ok: bool = False,
    contributing: str = "",
    pr_template: str = "",
    recent_pr_titles: list[str] | None = None,
    issue_title: str = "",
    issue_body: str = "",
    issue_number: int | None = None,
) -> MaintainerDraftContext:
    """DENY FLOW: copy only issue/diff/tests/guidelines. Drop entry why/scores."""
    title = (issue_title or "").strip()
    body = (issue_body or "").strip()
    number = issue_number
    commands = list(test_commands or [])
    changed = list(files or [])
    if structured is not None:
        if not title:
            title = (structured.issue_title or "").strip()
        if not body:
            body = (structured.issue_body or "").strip()
        if number is None:
            number = structured.issue_number
        if not commands:
            commands = list(structured.test_commands or [])
        if not changed:
            changed = list(structured.relevant_files or [])
        if title and _LEAK_HINT.search(title):
            title = (structured.issue_title or "").strip()
    language = infer_maintainer_language(
        contributing=contributing,
        issue_title=title,
        issue_body=body,
        recent_pr_titles=recent_pr_titles,
    )
    return MaintainerDraftContext(
        repository=repository,
        issue_number=number,
        issue_title=title,
        issue_body=body,
        diff=diff or "",
        changed_files=changed,
        test_commands=commands,
        tests_ok=bool(tests_ok),
        contributing=contributing or "",
        pr_template=pr_template or "",
        recent_pr_titles=list(recent_pr_titles or []),
        language=language,
    )
