"""Structured task Foreshadow hands a coding backend. Not 'fix the repo'."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StructuredTask(BaseModel):
    repository: str
    task: str
    evidence: list[str] = Field(default_factory=list)
    issue_number: int | None = None
    issue_url: str | None = None
    expected_behavior: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    contribution_rules: list[str] = Field(default_factory=list)
    test_commands: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    why: str = ""

    def to_prompt(self) -> str:
        lines = [
            f"Repository: {self.repository}",
            f"Task: {self.task}",
        ]
        if self.issue_number is not None:
            lines.append(f"Related issue: #{self.issue_number}")
        if self.issue_url:
            lines.append(f"Issue URL: {self.issue_url}")
        if self.why:
            lines.append(f"Why this task: {self.why}")
        if self.evidence:
            lines.append("Evidence:")
            lines.extend(f"- {item}" for item in self.evidence)
        if self.expected_behavior:
            lines.append(f"Expected behavior: {self.expected_behavior}")
        if self.acceptance_criteria:
            lines.append("Acceptance criteria:")
            lines.extend(f"- {item}" for item in self.acceptance_criteria)
        if self.relevant_files:
            lines.append("Relevant files:")
            lines.extend(f"- {item}" for item in self.relevant_files)
        if self.contribution_rules:
            lines.append("Contribution rules:")
            lines.extend(f"- {item}" for item in self.contribution_rules)
        if self.test_commands:
            lines.append("Test commands:")
            lines.extend(f"- `{item}`" for item in self.test_commands)
        if self.constraints:
            lines.append("Constraints:")
            lines.extend(f"- {item}" for item in self.constraints)
        if self.forbidden_actions:
            lines.append("Forbidden actions:")
            lines.extend(f"- {item}" for item in self.forbidden_actions)
        lines.append(
            "When done, print COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT as the only command."
        )
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


DEFAULT_FORBIDDEN = (
    "git push",
    "git remote add",
    "gh pr create",
    "gh issue comment",
    "call the GitHub HTTP API with a credential",
    "read host SSH keys or .git-credentials",
    "print environment secrets",
)


def from_entry(
    full_name: str,
    entry: dict[str, Any] | None,
    *,
    extra: dict[str, Any] | None = None,
) -> StructuredTask:
    """Build a task from Entry Strategy Plan A. Does not invent issue numbers."""
    extra = extra or {}
    rec = {}
    policy = {}
    if isinstance(entry, dict):
        rec = (
            entry.get("recommended")
            if isinstance(entry.get("recommended"), dict)
            else {}
        )
        policy = entry.get("policy") if isinstance(entry.get("policy"), dict) else {}
    issue_n = rec.get("issue_number")
    try:
        issue_n_i = int(issue_n) if issue_n is not None else None
    except (TypeError, ValueError):
        issue_n_i = None
    title = str(rec.get("title") or extra.get("task") or "").strip()
    summary = str(rec.get("summary_zh") or rec.get("summary") or "").strip()
    why = str(rec.get("why") or extra.get("why") or "")
    if isinstance(rec.get("why"), list):
        why = "; ".join(str(x) for x in rec["why"] if str(x).strip())
    evidence = [str(x) for x in (rec.get("evidence") or extra.get("evidence") or [])]
    if evidence and isinstance(evidence[0], dict):
        evidence = [
            str(item.get("url") or item.get("id") or item)
            for item in rec.get("evidence") or []
            if isinstance(item, dict)
        ]
    rules = []
    if policy.get("wants_issue_first"):
        rules.append("Repository prefers an issue before a PR. Link the issue.")
    if policy.get("cla") is True:
        rules.append("CLA required.")
    if policy.get("dco") is True:
        rules.append("DCO / signed-off-by required.")
    files = [str(x) for x in extra.get("relevant_files") or rec.get("files") or []]
    tests = [str(x) for x in extra.get("test_commands") or []]
    issue_url = extra.get("issue_url")
    if issue_n_i and not issue_url:
        issue_url = f"https://github.com/{full_name}/issues/{issue_n_i}"
    task_text = title or summary or str(extra.get("task") or "")
    return StructuredTask(
        repository=full_name,
        task=task_text,
        evidence=evidence or [str(x) for x in extra.get("evidence") or []],
        issue_number=issue_n_i,
        issue_url=str(issue_url) if issue_url else None,
        expected_behavior=str(extra.get("expected_behavior") or ""),
        acceptance_criteria=[str(x) for x in extra.get("acceptance_criteria") or []],
        constraints=[str(x) for x in extra.get("constraints") or []],
        relevant_files=files,
        contribution_rules=rules,
        test_commands=tests,
        forbidden_actions=list(DEFAULT_FORBIDDEN),
        why=why or str(extra.get("why") or ""),
    )
