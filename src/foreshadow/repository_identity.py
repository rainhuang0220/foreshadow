"""Read-only normalization of a GitHub remote identity."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_UPSTREAM = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def github_repository_name(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("git@github.com:"):
        part = url[len("git@github.com:") :]
    else:
        parsed = urlparse(url)
        if parsed.hostname != "github.com" or parsed.scheme not in {
            "https",
            "ssh",
            "git",
        }:
            return None
        part = parsed.path.lstrip("/")
    part = part.removesuffix(".git")
    return part if _UPSTREAM.fullmatch(part) else None
