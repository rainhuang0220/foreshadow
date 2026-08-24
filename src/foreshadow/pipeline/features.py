from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from foreshadow.clock import Clock
from foreshadow.models import FeaturesBlob

VelocitySource = Literal["exact", "nearest-1d"]
EPS = 0.5
README_CHARS = 20_000
SOURCE_DIRS = frozenset({"src", "lib", "crates", "app", "cmd", "pkg"})
META_EXACT = frozenset({".gitignore", ".gitattributes"})
SOURCE_EXTS = (
    ".py",
    ".rs",
    ".go",
    ".ts",
    ".js",
    ".c",
    ".h",
    ".cpp",
    ".cc",
    ".zig",
    ".java",
    ".rb",
    ".ex",
)
# P0 language manifests (exhaustive). Gemfile-only is not H3.
MANIFESTS = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "Pipfile",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Cargo.toml",
        "go.mod",
        "go.sum",
        "CMakeLists.txt",
        "meson.build",
        "Makefile",
        "makefile",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "Gemfile",
        "composer.json",
        "mix.exs",
        "dune-project",
        "Package.swift",
        "pubspec.yaml",
        "flake.nix",
        "default.nix",
        "BUILD",
        "BUILD.bazel",
    }
)
INSTALL_LITERALS = (
    "pip install",
    "pipx",
    "uv add",
    "poetry add",
    "cargo add",
    "cargo install",
    "npm i",
    "npm install",
    "pnpm",
    "yarn add",
    "bun add",
    "go get",
    "go install",
    "gem install",
    "composer require",
    "docker pull",
    "docker run",
    "brew install",
    "git clone",
    "huggingface-cli",
    "ollama pull",
    "mlx",
)
_CURL_INSTALL = re.compile(r"curl .* \| (ba)?sh", re.IGNORECASE)
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_HTML_IMAGE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_IMG_EXT = re.compile(r"\.(?:gif|png|jpg|jpeg|webp|svg)\b", re.IGNORECASE)
_FENCE = re.compile(
    r"^(?P<fence>`{3,}|~{3,})(?P<info>[^\n]*)\n(?P<body>.*?)(?:\n)?(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class SnapshotPoint:
    date: date
    stars: int | None
    forks: int | None
    pushed_at: datetime | None


@dataclass(frozen=True)
class Windows:
    v7: float | None
    v30: float | None
    v90: float | None
    rel_growth_7d: float | None
    accel_ratio: float | None
    lifetime_star_rate: float | None
    v7_source: VelocitySource | None
    v30_source: VelocitySource | None
    v90_source: VelocitySource | None
    rel_growth_30d: float | None
    v7_over_stock: float | None
    is_accelerating: bool


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def clip01(x: float) -> float:
    return clip(x, 0.0, 1.0)


def star_velocity(
    snapshots: list[SnapshotPoint],
    today: date,
    n: int,
    slack_days: int,
) -> tuple[float | None, VelocitySource | None]:
    velocity, source, _rel = _window(snapshots, today, n, slack_days)
    return velocity, source


def compute_windows(
    snapshots: list[SnapshotPoint],
    clock: Clock,
    created_at: date | datetime | None,
    slack_days: int,
) -> Windows:
    today = clock.today()
    age_days = _age_days(today, created_at)
    today_snap = _snapshot_on(snapshots, today)
    stars = today_snap.stars if today_snap is not None else None
    lifetime = (
        (stars / age_days) if stars is not None and age_days is not None else None
    )

    v7, v7_source, rel7 = _dated_window(snapshots, today, 7, slack_days, age_days)
    v30, v30_source, rel30 = _dated_window(snapshots, today, 30, slack_days, age_days)
    v90, v90_source, _rel90 = _dated_window(snapshots, today, 90, slack_days, age_days)

    if v7 is not None and v30 is not None:
        accel = v7 / max(v30, EPS)
    else:
        accel = None
    over_stock = (v7 / max(stars, 1)) if v7 is not None and stars is not None else None
    accelerating = is_accelerating(
        v7=v7,
        v30=v30,
        rel_growth_7d=rel7,
        accel_ratio=accel,
        lifetime_star_rate=lifetime,
        stars=stars,
    )
    return Windows(
        v7=v7,
        v30=v30,
        v90=v90,
        rel_growth_7d=rel7,
        accel_ratio=accel,
        lifetime_star_rate=lifetime,
        v7_source=v7_source,
        v30_source=v30_source,
        v90_source=v90_source,
        rel_growth_30d=rel30,
        v7_over_stock=over_stock,
        is_accelerating=accelerating,
    )


def is_accelerating(
    *,
    v7: float | None,
    v30: float | None,
    rel_growth_7d: float | None,
    accel_ratio: float | None,
    lifetime_star_rate: float | None,
    stars: int | None,
) -> bool:
    if v7 is None or rel_growth_7d is None or stars is None:
        return False
    if v7 < 3 or rel_growth_7d < 0.15 or stars >= 20_000:
        return False
    if v30 is not None:
        return accel_ratio is not None and accel_ratio >= 1.8
    if lifetime_star_rate is None:
        return False
    return v7 >= 2 * lifetime_star_rate


def readme_install(text: str) -> int:
    body = text[:README_CHARS]
    lowered = body.lower()
    if any(verb in lowered for verb in INSTALL_LITERALS):
        return 1
    if _CURL_INSTALL.search(body):
        return 1
    return 0


def screenshot_only(text: str) -> bool:
    body = text[:README_CHARS]
    if readme_install(body):
        return False
    images = _count_images(body)
    if images < 2:
        return False
    n = len(body)
    if not (n < 2500 or images / max(n, 1) >= 1 / 400):
        return False
    return not _has_disqualifying_fence(body)


def is_readme_only_tree(names: list[str]) -> bool:
    bases = [_root_name(name) for name in names]
    if any(base in MANIFESTS for base in bases):
        return False
    if any(base.lower() in SOURCE_DIRS for base in bases):
        return False
    source_files = [base for base in bases if _is_source_file(base)]
    if len(source_files) >= 2:
        return False
    for base in bases:
        if _is_source_file(base) or _is_meta_name(base):
            continue
        return False
    return True


def is_readme_only_blob(blob: FeaturesBlob) -> bool | None:
    """H3 tree heuristic from FeaturesBlob.tree_names. None if missing (not False)."""
    if blob.tree_names is None:
        return None
    return is_readme_only_tree(blob.tree_names)


def _dated_window(
    snapshots: list[SnapshotPoint],
    today: date,
    n: int,
    slack_days: int,
    age_days: int | None,
) -> tuple[float | None, VelocitySource | None, float | None]:
    if age_days is not None and age_days < n:
        return None, None, None
    return _window(snapshots, today, n, slack_days)


def _window(
    snapshots: list[SnapshotPoint],
    today: date,
    n: int,
    slack_days: int,
) -> tuple[float | None, VelocitySource | None, float | None]:
    today_snap = _snapshot_on(snapshots, today)
    if today_snap is None or today_snap.stars is None:
        return None, None, None
    past, source = _lookup(snapshots, today, n, slack_days)
    if past is None or past.stars is None:
        return None, None, None
    delta = today_snap.stars - past.stars
    velocity = delta / n
    rel = delta / max(past.stars, 10)
    return velocity, source, rel


def _lookup(
    snapshots: list[SnapshotPoint],
    today: date,
    n: int,
    slack_days: int,
) -> tuple[SnapshotPoint | None, VelocitySource | None]:
    want = today - timedelta(days=n)
    eligible = [
        snap
        for snap in snapshots
        if snap.date <= want and (want - snap.date).days <= slack_days
    ]
    if not eligible:
        return None, None
    # Closest to want among date <= want is the latest date (ties → later).
    best = max(eligible, key=lambda snap: snap.date)
    source: VelocitySource = "exact" if best.date == want else "nearest-1d"
    return best, source


def _snapshot_on(snapshots: list[SnapshotPoint], day: date) -> SnapshotPoint | None:
    matches = [snap for snap in snapshots if snap.date == day]
    if not matches:
        return None
    return matches[-1]


def _age_days(today: date, created_at: date | datetime | None) -> int | None:
    if created_at is None:
        return None
    created = _as_utc_date(created_at)
    return max((today - created).days, 1)


def _as_utc_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(UTC).date()
    return value


def _count_images(body: str) -> int:
    md = _MD_IMAGE.findall(body)
    html = [tag for tag in _HTML_IMAGE.findall(body) if _IMG_EXT.search(tag)]
    return len(md) + len(html)


def _has_disqualifying_fence(body: str) -> bool:
    for match in _FENCE.finditer(body):
        info = match.group("info").strip()
        lang = info.split()[0].lower() if info else ""
        if lang in {"", "bash", "sh"}:
            continue
        fence_body = match.group("body").strip()
        if not fence_body or _is_git_clone_oneliner(fence_body):
            continue
        return True
    return False


def _is_git_clone_oneliner(body: str) -> bool:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return len(lines) == 1 and lines[0].lower().startswith("git clone")


def _root_name(name: str) -> str:
    return name.strip().rstrip("/").rsplit("/", 1)[-1]


def _is_source_file(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in SOURCE_EXTS)


def _is_meta_name(name: str) -> bool:
    if name in META_EXACT:
        return True
    lower = name.lower()
    return lower.startswith(("readme", "license", "copying"))
