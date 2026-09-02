"""Host-side quality gate for a contribution patch.

Runs on the artifact, never inside the sandbox. Rejects empty diffs,
typo/format-only spam, missing why, failed tests, and unrelated junk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from foreshadow.contribution.executor import ContributionJob, PatchArtifact

_SPAM_TASK = re.compile(
    r"(add a space|fix( a)? typos?|typo.?only|format.?only|whitespace only|"
    r"readme only|trailing spaces?|prettier|run black|lint only|"
    r"space in readme)",
    re.IGNORECASE,
)
_JUNK_PATH_PARTS = (
    ".github",
    "node_modules",
    "dist",
    "vendor",
    "__pycache__",
    ".venv",
)
_LICENSE_NAMES = frozenset(
    {"license", "license.md", "license.txt", "copying", "copying.md"}
)


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reasons: tuple[str, ...] = ()


def gate(job: ContributionJob, artifact: PatchArtifact) -> GateResult:
    reasons: list[str] = []
    prompt = _task_text(job)
    why = (artifact.why or job.why or str((job.task or {}).get("why") or "")).strip()
    diff = artifact.diff or ""
    files = list(artifact.files) or diff_files(diff)

    if not diff.strip():
        reasons.append("empty diff")
    if not artifact.tests_passed:
        reasons.append("tests did not pass")
    if not why:
        reasons.append("missing why")
    if _is_spam_task(prompt):
        reasons.append("typo/format-only spam")
    if diff.strip() and _is_whitespace_only_diff(diff):
        reasons.append("whitespace-only diff")
    if files and _is_readme_space_spam(files, diff, prompt):
        reasons.append("readme space/format spam")
    junk = _unrelated_junk(files, prompt)
    if junk:
        reasons.append("unrelated junk: " + ", ".join(junk))

    return GateResult(ok=not reasons, reasons=tuple(reasons))


def diff_files(diff: str) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for line in (diff or "").splitlines():
        name = ""
        if line.startswith("+++ b/"):
            name = line[6:].strip()
        elif line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4 and parts[3].startswith("b/"):
                name = parts[3][2:]
        if not name or name == "/dev/null" or name in seen:
            continue
        seen.add(name)
        files.append(name)
    return files


def _task_text(job: ContributionJob) -> str:
    task = job.task or {}
    bits = [
        str(task.get("prompt") or ""),
        str(task.get("title") or ""),
        str(task.get("why") or ""),
        str(job.why or ""),
    ]
    return " ".join(bits)


def _is_spam_task(prompt: str) -> bool:
    return bool(prompt and _SPAM_TASK.search(prompt))


def _is_readme_space_spam(files: list[str], diff: str, prompt: str) -> bool:
    names = [_basename(f).lower() for f in files]
    if not names:
        return False
    return all(n.startswith("readme") for n in names) and (
        _is_spam_task(prompt) or _is_whitespace_only_diff(diff)
    )


def _unrelated_junk(files: list[str], prompt: str) -> list[str]:
    hits: list[str] = []
    prompt_l = prompt.lower()
    for rel in files:
        parts = rel.replace("\\", "/").lower().split("/")
        base = parts[-1] if parts else rel.lower()
        if any(part in _JUNK_PATH_PARTS for part in parts):
            hits.append(rel)
            continue
        if base in _LICENSE_NAMES and "license" not in prompt_l:
            hits.append(rel)
    return hits


def _is_whitespace_only_diff(diff: str) -> bool:
    added: list[str] = []
    removed: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "diff ")):
            continue
        if line.startswith("@@"):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    if not added and not removed:
        return True
    return "".join(added).split() == "".join(removed).split()


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]
