"""Machine-local, explicit links to independent Git checkouts.

This module never creates a checkout or passes one to a mission executor.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import tempfile
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from foreshadow.paths import resolve_data_dir
from foreshadow.reviews import _resolve_local

_UPSTREAM = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class RegistryError(ValueError):
    """Invalid registry input or a duplicate enrollment."""


@dataclass(frozen=True)
class RepositoryEntry:
    upstream: str
    path: str | None = None


@dataclass(frozen=True)
class Registry:
    workspace_root: Path
    repositories: tuple[RepositoryEntry, ...]


def registry_path() -> Path:
    return resolve_data_dir() / "repositories.toml"


def _check_upstream(value: object) -> str:
    if not isinstance(value, str) or not _UPSTREAM.fullmatch(value):
        raise RegistryError("upstream must be a GitHub owner/name")
    return value


def _root(value: object) -> Path:
    if not isinstance(value, str) or not value or not Path(value).expanduser().is_absolute():
        raise RegistryError("workspace_root must be an absolute path")
    try:
        return Path(value).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise RegistryError(f"invalid workspace_root: {exc}") from exc


def checkout_path(root: Path, path: str) -> Path:
    """Reject lexical escapes and symlink escapes, including existing parents."""
    if not isinstance(path, str) or not path or Path(path).is_absolute():
        raise RegistryError("path must be relative to workspace_root")
    parts = Path(path).parts
    if any(part in {".", ".."} for part in parts) or path.startswith("~"):
        raise RegistryError("path must not contain traversal")
    try:
        candidate = (root / path).resolve()
    except (OSError, RuntimeError) as exc:
        raise RegistryError(f"invalid path: {exc}") from exc
    if candidate == root or not candidate.is_relative_to(root):
        raise RegistryError("path escapes workspace_root")
    return candidate


def load_registry(path: Path | None = None) -> Registry | None:
    file = path or registry_path()
    if not file.exists():
        return None
    try:
        raw = tomllib.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise RegistryError(f"invalid repositories.toml: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) - {"version", "workspace_root", "repository"}:
        raise RegistryError("unknown repositories.toml field")
    if type(raw.get("version")) is not int or raw["version"] != 1:
        raise RegistryError("unsupported repositories.toml version (expected 1)")
    root = _root(raw.get("workspace_root"))
    items = raw.get("repository", [])
    if not isinstance(items, list):
        raise RegistryError("repository must be an array of tables")
    entries: list[RepositoryEntry] = []
    names: set[str] = set()
    paths: set[Path] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) - {"upstream", "path"}:
            raise RegistryError("invalid repository fields")
        name = _check_upstream(item.get("upstream"))
        if name.casefold() in names:
            raise RegistryError(f"duplicate upstream: {name}")
        names.add(name.casefold())
        local = item.get("path")
        if local is not None:
            resolved = checkout_path(root, local)
            if resolved in paths:
                raise RegistryError(f"duplicate checkout path: {local}")
            paths.add(resolved)
        entries.append(RepositoryEntry(name, local))
    return Registry(root, tuple(entries))


def identities(upstreams: Iterable[str]) -> dict[str, tuple[int, str, str] | None]:
    """Read existing repos/aliases through one read-only SQLite connection."""
    names = tuple(upstreams)
    db = resolve_data_dir() / "foreshadow.sqlite3"
    if not db.is_file():
        return dict.fromkeys(names)
    try:
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
            return {name: _resolve_local(conn, name) for name in names}
    except sqlite3.Error as exc:
        raise RegistryError(f"could not read existing repository identity: {exc}") from exc


def enroll(upstream: str, *, workspace_root: str | None, path: str | None) -> Registry:
    upstream = _check_upstream(upstream)
    current = load_registry()
    if current is None:
        if workspace_root is None:
            raise RegistryError("first enrollment requires --workspace-root")
        current = Registry(_root(workspace_root), ())
    elif workspace_root is not None and _root(workspace_root) != current.workspace_root:
        raise RegistryError("workspace_root differs from the existing registry")
    local = checkout_path(current.workspace_root, path) if path is not None else None
    known = identities([upstream, *(item.upstream for item in current.repositories)])
    new_identity = known[upstream]
    if new_identity:
        upstream = new_identity[2]
    for item in current.repositories:
        if item.upstream.casefold() == upstream.casefold():
            raise RegistryError(f"already enrolled: {item.upstream}")
        if local is not None and item.path is not None and checkout_path(current.workspace_root, item.path) == local:
            raise RegistryError(f"checkout path already enrolled: {item.path}")
        existing_identity = known[item.upstream]
        if new_identity and existing_identity and new_identity[0] == existing_identity[0]:
            raise RegistryError(f"repository already enrolled as {item.upstream}")
    updated = Registry(current.workspace_root, (*current.repositories, RepositoryEntry(upstream, path)))
    _save(updated)
    return updated


def _save(registry: Registry) -> None:
    file = registry_path()
    file.parent.mkdir(parents=True, exist_ok=True)
    lines = ["version = 1", f"workspace_root = {json.dumps(str(registry.workspace_root), ensure_ascii=False)}"]
    for item in registry.repositories:
        lines.extend(("", "[[repository]]", f"upstream = {json.dumps(item.upstream)}"))
        if item.path is not None:
            lines.append(f"path = {json.dumps(item.path, ensure_ascii=False)}")
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=file.parent, prefix=".repositories-", delete=False) as handle:
            temp_name = handle.name
            handle.write("\n".join(lines) + "\n")
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, file)
    finally:
        if temp_name is not None and os.path.exists(temp_name):
            os.unlink(temp_name)


def _git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, check=False, timeout=10,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _github_name(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("git@github.com:"):
        part = url[len("git@github.com:"):]
    else:
        parsed = urlparse(url)
        if parsed.hostname != "github.com" or parsed.scheme not in {"https", "ssh", "git"}:
            return None
        part = parsed.path.lstrip("/")
    part = part.removesuffix(".git")
    return part if _UPSTREAM.fullmatch(part) else None


def validate(
    registry: Registry, item: RepositoryEntry, *, expected_upstream: str | None = None
) -> tuple[str, str]:
    if item.path is None:
        return "remote-only", "no local checkout registered"
    repo = checkout_path(registry.workspace_root, item.path)
    if not repo.exists():
        return "missing", str(repo)
    if not repo.is_dir() or _git(repo, "rev-parse", "--show-toplevel") != str(repo):
        return "not-checkout", str(repo)
    origin = _github_name(_git(repo, "config", "--get", "remote.origin.url"))
    upstream = _github_name(_git(repo, "config", "--get", "remote.upstream.url"))
    expected = expected_upstream or item.upstream
    target = expected.casefold()
    if upstream and upstream.casefold() != target:
        return "mismatch", f"upstream remote={upstream}; expected={expected}"
    if upstream and upstream.casefold() == target and origin and origin.casefold() != target:
        return "fork", f"origin={origin}; upstream={upstream}"
    if origin and origin.casefold() == target or upstream and upstream.casefold() == target:
        return "ok", f"upstream={expected}"
    if origin:
        return "upstream-unverified", f"origin={origin}; expected upstream={expected}"
    return "upstream-unverified", f"no matching GitHub remote; expected upstream={expected}"
