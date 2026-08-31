"""Walk a cloned worktree. Never invent paths or commands."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        ".venv",
        "venv",
        "target",
        "vendor",
        ".tox",
        ".mypy_cache",
    }
)
SOURCE_EXT = frozenset(
    {".py", ".rs", ".go", ".ts", ".js", ".tsx", ".jsx", ".c", ".cpp", ".h", ".cc"}
)
TEST_NAME_HINTS = ("test_", "_test.", ".test.", "spec.", "_spec.")
SAFE_CMD = re.compile(
    r"^\s*(pytest|python3?(?:\s+-m\s+pytest)?|go\s+test|cargo\s+test)\b",
    re.IGNORECASE,
)
STOP_WORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "issue",
        "crash",
        "error",
        "fail",
        "empty",
        "when",
        "into",
    }
)


def enrich_inspect(
    clone_dir: Path | None,
    inspect: dict[str, Any] | None = None,
    cited: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add source/test files and issue commands that exist on disk or in GET body."""
    out = dict(inspect or {})
    if clone_dir is None or not Path(clone_dir).is_dir():
        out.setdefault("source_files", [])
        out.setdefault("test_files", [])
        out.setdefault("related_files", [])
        out.setdefault("issue_commands", [])
        return out
    files = list_worktree_files(Path(clone_dir))
    src = source_files(files)
    tests = test_files(files)
    ticket = _ticket_text(cited)
    out["source_files"] = src[:12]
    out["test_files"] = tests[:12]
    out["related_files"] = related_files(src, ticket)
    body = str((cited or {}).get("body") or "")
    out["issue_commands"] = commands_from_body(body)
    return out


def list_worktree_files(root: Path, *, limit: int = 80) -> list[str]:
    out: list[str] = []
    for dirpath, dirnames, filenames in Path(root).walk(follow_symlinks=False):
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        ]
        rel_dir = dirpath.relative_to(root)
        for name in filenames:
            if name.startswith("."):
                continue
            try:
                if (dirpath / name).is_symlink():
                    continue
            except OSError:
                continue
            rel = name if str(rel_dir) == "." else f"{rel_dir.as_posix()}/{name}"
            out.append(rel)
            if len(out) >= limit:
                return out
    return out


def source_files(files: list[str]) -> list[str]:
    return [f for f in files if Path(f).suffix.lower() in SOURCE_EXT]


def test_files(files: list[str]) -> list[str]:
    out: list[str] = []
    for path in files:
        low = path.replace("\\", "/").lower()
        name = Path(path).name.lower()
        in_test_dir = (
            "/tests/" in f"/{low}" or "/test/" in f"/{low}" or "/spec/" in f"/{low}"
        )
        looks_test = any(h in name for h in TEST_NAME_HINTS)
        if (in_test_dir or looks_test) and Path(path).suffix.lower() in SOURCE_EXT:
            out.append(path)
    return out


def related_files(files: list[str], ticket: str | None) -> list[str]:
    if not files:
        return []
    tokens = [
        t.lower()
        for t in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", ticket or "")
        if t.lower() not in STOP_WORDS
    ]
    hits: list[str] = []
    for path in files:
        blob = path.lower()
        if any(tok in blob for tok in tokens):
            hits.append(path)
    return (hits or files)[:4]


def commands_from_body(body: str | None) -> list[str]:
    if not body:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in body.splitlines():
        line = raw.strip().lstrip("$").strip("`").strip()
        low = line.lower()
        if any(
            bad in low
            for bad in ("curl ", "| sh", "| bash", "pip install", "npm install")
        ):
            continue
        if not SAFE_CMD.match(line):
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line[:160])
        if len(out) >= 5:
            break
    return out


def _ticket_text(cited: dict[str, Any] | None) -> str:
    cited = cited or {}
    return " ".join(str(cited.get(k) or "") for k in ("number", "title", "body"))
