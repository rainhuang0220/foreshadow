from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from foreshadow.clock import Clock
from foreshadow.config import DiscoverySettings
from foreshadow.github.client import GitHubError, graphql_marks_incomplete
from foreshadow.github.queries import HYDRATE_A_NODE, HYDRATE_B_NODE
from foreshadow.github.rest import (
    content_exists,
    fetch_commits,
    fetch_community_profile,
    fetch_contributors,
    fetch_root_contents,
    fetch_workflows,
    is_bot,
)
from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.direction import DirectionBag, load_direction_bags
from foreshadow.pipeline.features import (
    README_CHARS,
    is_readme_only_tree,
    readme_install,
    screenshot_only,
)

HELP_LABELS = frozenset(
    {
        "help wanted",
        "help-wanted",
        "good first issue",
        "good-first-issue",
        "documentation",
        "docs",
        "contribution welcome",
        "up for grabs",
    }
)
BUG_LABELS = frozenset({"bug", "crash", "defect", "regression"})
BUG_TITLE_RE = re.compile(
    r"(?i)(bug|crash|panic|segfault|regress|doesn'?t work|fails when|error when|npe|null pointer)"
)
USAGE_CLOSED_RE = re.compile(
    r"(?i)(how (do|can) i|fails when|not working|wrong result|timeout)"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
PUNCT_RE = re.compile(r"[^a-z0-9\s]+")
TEST_DIRS = frozenset({"test", "tests", "spec", "__tests__"})
EXT_ASSOC = frozenset({"NONE", "CONTRIBUTOR"})
MAINT_ASSOC = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


@dataclass
class HydratedRepo:
    node_id: str
    full_name: str
    name: str = ""
    owner: str = ""
    description: str | None = None
    language: str | None = None
    topics: list[str] = field(default_factory=list)
    stargazerCount: int = 0
    fork_count: int = 0
    pushed_at: datetime | None = None
    created_at: str | None = None
    is_fork: bool = False
    is_archived: bool = False
    is_disabled: bool = False
    is_empty: bool = False
    is_template: bool = False
    is_mirror: bool = False
    has_issues: bool | None = None
    license_spdx: str | None = None
    default_branch: str | None = None
    html_url: str | None = None
    database_id: int | None = None
    status: str = "active"
    hydrate_status: str = "ok"
    repo_id: int | None = None
    graphql: dict[str, Any] = field(default_factory=dict)
    features: FeaturesBlob | None = None
    contributor_count: int | None = None
    contributor_identified: int | None = None
    contributor_anon: int | None = None
    contributor_censored: int | None = None
    unique_committers_30d: int | None = None


def _get(repo: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(repo, Mapping) and name in repo and repo[name] is not None:
            return repo[name]
        if hasattr(repo, name):
            val = getattr(repo, name)
            if val is not None:
                return val
    return default


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def recency_bucket(pushed_at: Any, now: datetime | date) -> int:
    if pushed_at is None:
        return 0
    pushed = parse_dt(pushed_at)
    if pushed is None:
        return 0
    now_d = now.date() if isinstance(now, datetime) else now
    days = (now_d - pushed.date()).days
    if days <= 14:
        return 2
    if days <= 45:
        return 1
    return 0


def direction_keyword_hit(repo: Any, bags: Sequence[DirectionBag]) -> int:
    name = str(_get(repo, "name", default="") or "")
    desc = str(_get(repo, "description", default="") or "")
    topics = _get(repo, "topics", default=None) or []
    if isinstance(topics, str):
        topic_s = topics
    else:
        topic_s = " ".join(str(t) for t in topics)
    text = f"{name} {desc} {topic_s}".lower()
    for bag in bags:
        for kw in bag.keywords:
            if kw.lower() in text:
                return 1
    return 0


def pre_rank_key(
    repo: Any,
    cfg: DiscoverySettings | None = None,
    bags: Sequence[DirectionBag] | None = None,
    now: datetime | date | None = None,
) -> tuple:
    cfg = cfg or DiscoverySettings()
    bags = list(bags) if bags is not None else load_direction_bags()
    now = now or datetime.now(UTC)
    language = _get(repo, "language", default="") or ""
    lang_bonus = int(language in cfg.languages) if cfg.languages else 0
    node_id = str(_get(repo, "node_id", "id", default="") or "")
    return (
        direction_keyword_hit(repo, bags),
        recency_bucket(_get(repo, "pushed_at", "pushedAt"), now),
        lang_bonus,
        node_id,
    )


def _normalize_actions(watchlist_actions: Any) -> list[tuple[str, str]]:
    if watchlist_actions is None:
        return []
    if isinstance(watchlist_actions, Mapping):
        return [(str(k), str(v)) for k, v in watchlist_actions.items()]
    out: list[tuple[str, str]] = []
    for item in watchlist_actions:
        if isinstance(item, tuple) and len(item) >= 2:
            out.append((str(item[0]), str(item[1])))
        else:
            nid = getattr(item, "node_id", None)
            act = getattr(item, "action", None)
            if nid and act:
                out.append((str(nid), str(act)))
    return out


def phase_b_shortlist(
    candidates: Sequence[Any],
    watchlist_actions: Any,
    max_deep: int = 30,
    max_watchlist_deep: int = 20,
    *,
    cfg: DiscoverySettings | None = None,
    bags: Sequence[DirectionBag] | None = None,
    now: datetime | date | None = None,
    exclude_forks: bool = True,
) -> list[Any]:
    cfg = cfg or DiscoverySettings()
    bags = list(bags) if bags is not None else load_direction_bags()
    now = now or datetime.now(UTC)

    def dropped(repo: Any) -> bool:
        if _get(repo, "is_archived", "isArchived"):
            return True
        if _get(repo, "is_disabled", "isDisabled"):
            return True
        if _get(repo, "is_empty", "isEmpty"):
            return True
        if _get(repo, "status") == "not_found":
            return True
        return bool(exclude_forks and _get(repo, "is_fork", "isFork"))

    pool = [c for c in candidates if not dropped(c)]
    ordered = _normalize_actions(watchlist_actions)
    action_map = {nid: act for nid, act in ordered}

    def nid_of(repo: Any) -> str:
        return str(_get(repo, "node_id", "id", default="") or "")

    enter = {nid_of(c) for c in pool if action_map.get(nid_of(c)) == "enter"}
    rankable = {"watch", "interested", "investigate", "later"}
    w_order: list[str] = []
    seen: set[str] = set()
    in_pool = {nid_of(c) for c in pool}
    for nid, act in ordered:
        if act == "enter" or act not in rankable:
            continue
        if nid in in_pool and nid not in seen:
            w_order.append(nid)
            seen.add(nid)
    by_id = {nid_of(c): c for c in pool}
    phase: list[Any] = []
    taken: set[str] = set()
    for nid in w_order[:max_watchlist_deep]:
        repo = by_id.get(nid)
        if repo is None:
            continue
        phase.append(repo)
        taken.add(nid)
    rest = [c for c in pool if nid_of(c) not in taken and nid_of(c) not in enter]
    rest.sort(key=lambda c: pre_rank_key(c, cfg=cfg, bags=bags, now=now), reverse=True)
    for repo in rest:
        if len(phase) >= max_deep:
            break
        phase.append(repo)
        taken.add(nid_of(repo))
    return phase


def unique_committers_30d(commits: Sequence[Mapping[str, Any]]) -> int:
    """Unique human authors. Never len(commits)."""
    authors: set[str] = set()
    for row in commits:
        user = row.get("author") if isinstance(row, Mapping) else None
        login = None
        type_ = None
        if isinstance(user, Mapping):
            login = user.get("login")
            type_ = user.get("type")
        if is_bot(login, type_):
            continue
        if login:
            authors.add("login:" + str(login).lower())
            continue
        commit = row.get("commit") if isinstance(row, Mapping) else None
        ca = commit.get("author") if isinstance(commit, Mapping) else None
        if not isinstance(ca, Mapping):
            continue
        name = str(ca.get("name") or "")
        email = str(ca.get("email") or "")
        if is_bot(name) or "[bot]" in name.lower():
            continue
        if email:
            authors.add("email:" + email.lower())
        elif name:
            authors.add("name:" + name.lower())
    return len(authors)


def _is_not_found(exc: GitHubError) -> bool:
    if exc.status in {404, 410, 451}:
        return True
    return exc.reason == "http_404"


def extract_repo(body: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    repo = data.get("node")
    if repo is None:
        repo = data.get("repository")
    if not isinstance(repo, dict):
        return None
    if not repo.get("id") and not repo.get("nameWithOwner"):
        return None
    return repo


def hydrate_a_node(
    client: Any, node_id: str, *, force: bool = False
) -> tuple[dict | None, GitHubError | None]:
    try:
        body = client.graphql(HYDRATE_A_NODE, {"id": node_id}, force=force)
    except GitHubError as exc:
        return None, exc
    return body, None


def hydrate_b_node(
    client: Any, node_id: str, *, force: bool = False
) -> tuple[dict | None, GitHubError | None]:
    try:
        body = client.graphql(HYDRATE_B_NODE, {"id": node_id}, force=force)
    except GitHubError as exc:
        return None, exc
    return body, None


def from_graphql(
    repo: dict[str, Any],
    *,
    repo_id: int | None = None,
    hydrate_status: str = "ok",
    status: str = "active",
) -> HydratedRepo:
    full = str(repo.get("nameWithOwner") or "")
    owner, name = _split_name(full)
    lang = repo.get("primaryLanguage")
    language = lang.get("name") if isinstance(lang, dict) else None
    lic = repo.get("licenseInfo")
    spdx = lic.get("spdxId") if isinstance(lic, dict) else None
    ref = repo.get("defaultBranchRef")
    branch = ref.get("name") if isinstance(ref, dict) else None
    topics: list[str] = []
    raw_topics = repo.get("repositoryTopics") or {}
    nodes = raw_topics.get("nodes") if isinstance(raw_topics, dict) else None
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("topic"), dict):
                tname = node["topic"].get("name")
                if tname:
                    topics.append(str(tname))
    return HydratedRepo(
        node_id=str(repo.get("id") or ""),
        full_name=full,
        name=name,
        owner=owner,
        description=repo.get("description"),
        language=language,
        topics=topics,
        stargazerCount=int(repo.get("stargazerCount") or 0),
        fork_count=int(repo.get("forkCount") or 0),
        pushed_at=parse_dt(repo.get("pushedAt")),
        created_at=repo.get("createdAt"),
        is_fork=bool(repo.get("isFork")),
        is_archived=bool(repo.get("isArchived")),
        is_disabled=bool(repo.get("isDisabled")),
        is_empty=bool(repo.get("isEmpty")),
        is_template=bool(repo.get("isTemplate")),
        is_mirror=bool(repo.get("isMirror")),
        has_issues=repo.get("hasIssuesEnabled"),
        license_spdx=spdx,
        default_branch=branch,
        html_url=repo.get("url"),
        database_id=repo.get("databaseId"),
        status=status,
        hydrate_status=hydrate_status,
        repo_id=repo_id,
        graphql=repo,
    )


def apply_identity(
    conn: sqlite3.Connection,
    client: Any,
    identity_ids: set[str] | Sequence[str],
    search_hits: Sequence[Any],
    *,
    clock: Clock | None = None,
    force: bool = False,
) -> dict[str, HydratedRepo]:
    clock = clock or Clock()
    now = clock.now().isoformat()
    hits_by_name: dict[str, list[Any]] = {}
    for hit in search_hits:
        fn = getattr(hit, "full_name", None) or (
            hit.get("full_name") if isinstance(hit, Mapping) else None
        )
        if fn:
            hits_by_name.setdefault(str(fn), []).append(hit)
    out: dict[str, HydratedRepo] = {}
    for nid in identity_ids:
        row = conn.execute(
            "SELECT id, node_id, full_name, status FROM repos WHERE node_id=?",
            (nid,),
        ).fetchone()
        body, err = hydrate_a_node(client, nid, force=force)
        repo = extract_repo(body) if body is not None else None
        missing = err is not None and _is_not_found(err)
        if err is not None and not missing:
            if row:
                out[nid] = HydratedRepo(
                    node_id=nid,
                    full_name=row[2],
                    repo_id=row[0],
                    status=row[3],
                    hydrate_status="failed",
                )
            continue
        if missing or repo is None:
            occupants = []
            if row:
                occupants = [
                    h for h in hits_by_name.get(row[2], []) if _hit_node_id(h) != nid
                ]
            _suffix_then_insert(conn, row, occupants, now)
            if row:
                out[nid] = HydratedRepo(
                    node_id=nid,
                    full_name=f"{row[2].split('#deleted-', 1)[0]}#deleted-{nid}"
                    if "#deleted-" not in row[2]
                    else row[2],
                    repo_id=row[0],
                    status="not_found",
                    hydrate_status="not_found",
                )
            continue
        if row:
            _apply_live(conn, row, repo, now)
            out[nid] = from_graphql(
                repo,
                repo_id=row[0],
                hydrate_status="incomplete"
                if graphql_marks_incomplete(body or {})
                else "ok",
            )
        else:
            repo_id = upsert_repo_from_graphql(conn, repo, now)
            out[nid] = from_graphql(repo, repo_id=repo_id)
    return out


def _hit_node_id(hit: Any) -> str:
    if isinstance(hit, Mapping):
        return str(hit.get("node_id") or hit.get("id") or "")
    return str(getattr(hit, "node_id", "") or "")


def _split_name(full: str) -> tuple[str, str]:
    base = full.split("#", 1)[0]
    if "/" in base:
        owner, name = base.split("/", 1)
        return owner, name
    return "", base


def _suffix_row(
    conn: sqlite3.Connection, repo_id: int, node_id: str, full_name: str, now: str
) -> str:
    base = full_name.split("#deleted-", 1)[0]
    suffixed = (
        full_name if "#deleted-" in full_name else f"{full_name}#deleted-{node_id}"
    )
    conn.execute(
        "INSERT OR IGNORE INTO repo_aliases(repo_id, full_name, seen_at) VALUES (?,?,?)",
        (repo_id, base, now),
    )
    conn.execute(
        "UPDATE repos SET full_name=?, status='not_found', last_seen_at=? WHERE id=?",
        (suffixed, now, repo_id),
    )
    return suffixed


def _suffix_then_insert(
    conn: sqlite3.Connection,
    row: tuple | None,
    occupants: Sequence[Any],
    now: str,
) -> None:
    conn.execute("SAVEPOINT ident")
    try:
        if row is not None:
            _suffix_row(conn, row[0], row[1], row[2], now)
        for occ in occupants:
            nid = _hit_node_id(occ)
            if not nid:
                continue
            exists = conn.execute(
                "SELECT 1 FROM repos WHERE node_id=?", (nid,)
            ).fetchone()
            if exists is None:
                insert_hit(conn, occ, now)
        conn.execute("RELEASE ident")
    except Exception:
        conn.execute("ROLLBACK TO ident")
        conn.execute("RELEASE ident")
        raise


def _apply_live(
    conn: sqlite3.Connection, row: tuple, repo: dict[str, Any], now: str
) -> None:
    repo_id, _node_id, old_name, _status = row
    new_name = str(repo.get("nameWithOwner") or old_name)
    if new_name != old_name:
        other = conn.execute(
            "SELECT id, node_id, status, full_name FROM repos WHERE full_name=? AND id!=?",
            (new_name, repo_id),
        ).fetchone()
        if other is not None:
            _suffix_row(conn, other[0], other[1], other[3], now)
        conn.execute(
            "INSERT OR IGNORE INTO repo_aliases(repo_id, full_name, seen_at) VALUES (?,?,?)",
            (repo_id, old_name.split("#deleted-", 1)[0], now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO repo_aliases(repo_id, full_name, seen_at) VALUES (?,?,?)",
            (repo_id, new_name, now),
        )
    update_repo_from_graphql(conn, repo_id, repo, now, full_name=new_name)


def insert_hit(conn: sqlite3.Connection, hit: Any, now: str) -> int:
    if isinstance(hit, Mapping):
        nid = str(hit.get("node_id") or "")
        full = str(hit.get("full_name") or "")
        database_id = hit.get("database_id")
        url = hit.get("url")
        desc = hit.get("description")
        created = hit.get("created_at")
        language = hit.get("language")
        license_spdx = hit.get("license_spdx")
        is_fork = int(bool(hit.get("is_fork")))
        is_archived = int(bool(hit.get("is_archived")))
        is_disabled = int(bool(hit.get("is_disabled")))
        is_empty = int(bool(hit.get("is_empty")))
        is_mirror = int(bool(hit.get("is_mirror")))
        has_issues = hit.get("has_issues")
        raw = hit.get("raw") if isinstance(hit.get("raw"), dict) else {}
    else:
        nid = str(getattr(hit, "node_id", "") or "")
        full = str(getattr(hit, "full_name", "") or "")
        database_id = getattr(hit, "database_id", None)
        url = getattr(hit, "url", None)
        desc = getattr(hit, "description", None)
        created = getattr(hit, "created_at", None)
        language = getattr(hit, "language", None)
        license_spdx = getattr(hit, "license_spdx", None)
        is_fork = int(bool(getattr(hit, "is_fork", False)))
        is_archived = int(bool(getattr(hit, "is_archived", False)))
        is_disabled = int(bool(getattr(hit, "is_disabled", False)))
        is_empty = int(bool(getattr(hit, "is_empty", False)))
        is_mirror = int(bool(getattr(hit, "is_mirror", False)))
        has_issues = getattr(hit, "has_issues", None)
        raw = (
            getattr(hit, "raw", None)
            if isinstance(getattr(hit, "raw", None), dict)
            else {}
        )
    owner, name = _split_name(full)
    other = conn.execute(
        "SELECT id, node_id, full_name FROM repos WHERE full_name=?", (full,)
    ).fetchone()
    if other is not None:
        _suffix_row(conn, other[0], other[1], other[2], now)
    has_issues_i = None if has_issues is None else int(bool(has_issues))
    dbid = database_id or (raw.get("databaseId") if raw else None)
    conn.execute(
        """
        INSERT INTO repos(
          node_id, database_id, full_name, owner, name, html_url, description,
          language, license_spdx, created_at, default_branch, has_issues,
          is_fork, is_archived, is_disabled, is_empty, is_template, is_mirror,
          status, first_seen_at, last_seen_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            nid,
            dbid,
            full,
            owner,
            name,
            url,
            desc,
            language,
            license_spdx,
            created,
            None,
            has_issues_i,
            is_fork,
            is_archived,
            is_disabled,
            is_empty,
            0,
            is_mirror,
            "active",
            now,
            now,
        ),
    )
    return int(
        conn.execute("SELECT id FROM repos WHERE node_id=?", (nid,)).fetchone()[0]
    )


def upsert_repo_from_graphql(
    conn: sqlite3.Connection, repo: dict[str, Any], now: str
) -> int:
    nid = str(repo.get("id") or "")
    existing = conn.execute(
        "SELECT id, full_name FROM repos WHERE node_id=?", (nid,)
    ).fetchone()
    if existing:
        _apply_live(conn, (existing[0], nid, existing[1], "active"), repo, now)
        return int(existing[0])
    full = str(repo.get("nameWithOwner") or "")
    other = conn.execute(
        "SELECT id, node_id, full_name FROM repos WHERE full_name=?", (full,)
    ).fetchone()
    if other is not None:
        _suffix_row(conn, other[0], other[1], other[2], now)
    fields = _repo_tuple(repo, now)
    conn.execute(
        """
        INSERT INTO repos(
          node_id, database_id, full_name, owner, name, html_url, description,
          language, license_spdx, created_at, default_branch, has_issues,
          is_fork, is_archived, is_disabled, is_empty, is_template, is_mirror,
          status, first_seen_at, last_seen_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        fields,
    )
    return int(
        conn.execute("SELECT id FROM repos WHERE node_id=?", (nid,)).fetchone()[0]
    )


def update_repo_from_graphql(
    conn: sqlite3.Connection,
    repo_id: int,
    repo: dict[str, Any],
    now: str,
    *,
    full_name: str | None = None,
) -> None:
    full = full_name or str(repo.get("nameWithOwner") or "")
    owner, name = _split_name(full)
    lang = repo.get("primaryLanguage")
    language = lang.get("name") if isinstance(lang, dict) else None
    lic = repo.get("licenseInfo")
    spdx = lic.get("spdxId") if isinstance(lic, dict) else None
    ref = repo.get("defaultBranchRef")
    branch = ref.get("name") if isinstance(ref, dict) else None
    has_issues = repo.get("hasIssuesEnabled")
    has_issues_i = None if has_issues is None else int(bool(has_issues))
    conn.execute(
        """
        UPDATE repos SET
          database_id=?, full_name=?, owner=?, name=?, html_url=?, description=?,
          language=?, license_spdx=?, created_at=?, default_branch=?, has_issues=?,
          is_fork=?, is_archived=?, is_disabled=?, is_empty=?, is_template=?,
          is_mirror=?, status='active', last_seen_at=?
        WHERE id=?
        """,
        (
            repo.get("databaseId"),
            full,
            owner,
            name,
            repo.get("url"),
            repo.get("description"),
            language,
            spdx,
            repo.get("createdAt"),
            branch,
            has_issues_i,
            int(bool(repo.get("isFork"))),
            int(bool(repo.get("isArchived"))),
            int(bool(repo.get("isDisabled"))),
            int(bool(repo.get("isEmpty"))),
            int(bool(repo.get("isTemplate"))),
            int(bool(repo.get("isMirror"))),
            now,
            repo_id,
        ),
    )


def _repo_tuple(repo: dict[str, Any], now: str) -> tuple:
    full = str(repo.get("nameWithOwner") or "")
    owner, name = _split_name(full)
    lang = repo.get("primaryLanguage")
    language = lang.get("name") if isinstance(lang, dict) else None
    lic = repo.get("licenseInfo")
    spdx = lic.get("spdxId") if isinstance(lic, dict) else None
    ref = repo.get("defaultBranchRef")
    branch = ref.get("name") if isinstance(ref, dict) else None
    has_issues = repo.get("hasIssuesEnabled")
    has_issues_i = None if has_issues is None else int(bool(has_issues))
    return (
        repo.get("id"),
        repo.get("databaseId"),
        full,
        owner,
        name,
        repo.get("url"),
        repo.get("description"),
        language,
        spdx,
        repo.get("createdAt"),
        branch,
        has_issues_i,
        int(bool(repo.get("isFork"))),
        int(bool(repo.get("isArchived"))),
        int(bool(repo.get("isDisabled"))),
        int(bool(repo.get("isEmpty"))),
        int(bool(repo.get("isTemplate"))),
        int(bool(repo.get("isMirror"))),
        "active",
        now,
        now,
    )


def census_contributors(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[int, int, int, int]:
    identified = 0
    anon = 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if row.get("type") == "Anonymous" or not row.get("login"):
            anon += 1
        else:
            identified += 1
    censored = 1 if identified >= 500 else 0
    return identified + anon, identified, anon, censored


def hydrate_phase_b_rest(
    client: Any,
    owner: str,
    name: str,
    clock: Clock,
    *,
    is_fork: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "contributors": None,
        "commits": None,
        "contents": None,
        "workflows": None,
        "community": None,
    }
    try:
        out["contributors"] = fetch_contributors(client, owner, name)
    except GitHubError:
        pass
    try:
        out["commits"] = fetch_commits(
            client, owner, name, clock.now() - timedelta(days=30)
        )
    except GitHubError:
        pass
    try:
        out["contents"] = fetch_root_contents(client, owner, name)
    except GitHubError:
        pass
    try:
        out["workflows"] = fetch_workflows(client, owner, name)
    except GitHubError:
        pass
    if not is_fork:
        try:
            out["community"] = fetch_community_profile(client, owner, name)
        except GitHubError:
            pass
    contents = out["contents"] if isinstance(out["contents"], list) else []
    names = {
        str(item.get("name"))
        for item in contents
        if isinstance(item, dict) and item.get("name")
    }
    for extra in ("tests", "test", "src"):
        if extra in names:
            try:
                content_exists(client, owner, name, extra)
            except GitHubError:
                pass
    return out


def build_features_blob(
    repo: dict[str, Any],
    rest: Mapping[str, Any],
) -> FeaturesBlob:
    readme_obj = repo.get("readme")
    readme_text = ""
    if isinstance(readme_obj, dict):
        readme_text = str(readme_obj.get("text") or "")[:README_CHARS]
    sample = repo.get("issuesOpenSample")
    nodes = sample.get("nodes") if isinstance(sample, dict) else None
    open_sample_landed = isinstance(nodes, list)
    nodes = nodes if open_sample_landed else []
    closed = repo.get("issuesClosedSample")
    closed_nodes = closed.get("nodes") if isinstance(closed, dict) else None
    closed_sample_landed = isinstance(closed_nodes, list)
    closed_nodes = closed_nodes if closed_sample_landed else []

    bots: list[str] = []
    authors: set[str] = set()
    authors_ext: set[str] = set()
    bug_n = 0
    talk_n = 0
    help_n = 0
    unassigned_help = 0
    maint_hits = 0
    help_titles: list[str] = []
    open_titles: list[str] = []
    for issue in nodes:
        if not isinstance(issue, dict):
            continue
        title = str(issue.get("title") or "")
        number = issue.get("number")
        open_titles.append(title)
        author = issue.get("author") if isinstance(issue.get("author"), dict) else {}
        login = author.get("login") if isinstance(author, dict) else None
        assoc = str(issue.get("authorAssociation") or "")
        if is_bot(login, None):
            if login:
                bots.append(str(login))
            login = None
        if login:
            authors.add(str(login).lower())
            if assoc in EXT_ASSOC:
                authors_ext.add(str(login).lower())
        labels = _label_names(issue)
        if labels & BUG_LABELS or BUG_TITLE_RE.search(title):
            bug_n += 1
        if labels & HELP_LABELS:
            help_n += 1
            help_titles.append(f"#{number} {title}" if number is not None else title)
            assignees = (
                issue.get("assignees")
                if isinstance(issue.get("assignees"), dict)
                else {}
            )
            if int(assignees.get("totalCount") or 0) == 0:
                unassigned_help += 1
        comments = (
            issue.get("comments") if isinstance(issue.get("comments"), dict) else {}
        )
        cnodes = comments.get("nodes") if isinstance(comments, dict) else None
        talked = False
        maint = False
        if isinstance(cnodes, list):
            for cmt in cnodes:
                if not isinstance(cmt, dict):
                    continue
                cauth = cmt.get("author") if isinstance(cmt.get("author"), dict) else {}
                clogin = cauth.get("login") if isinstance(cauth, dict) else None
                cassoc = str(cmt.get("authorAssociation") or "")
                if clogin and login and str(clogin).lower() != str(login).lower():
                    talked = True
                if cassoc in MAINT_ASSOC:
                    maint = True
        if talked:
            talk_n += 1
        if maint:
            maint_hits += 1
    usage_closed_n = 0
    for issue in closed_nodes:
        if isinstance(issue, dict) and USAGE_CLOSED_RE.search(
            str(issue.get("title") or "")
        ):
            usage_closed_n += 1

    contents_raw = rest.get("contents")
    contents_known = isinstance(contents_raw, list)
    contents = contents_raw if contents_known else []
    tree_names = (
        [
            str(item.get("name"))
            for item in contents
            if isinstance(item, dict) and item.get("name")
        ]
        if contents_known
        else None
    )
    names_for_tree = tree_names or []
    workflows = (
        rest.get("workflows") if isinstance(rest.get("workflows"), dict) else None
    )
    if workflows is None:
        has_workflows = None
        gap_ci = None
    else:
        wf_list = workflows.get("workflows")
        wf_count = workflows.get("total_count")
        try:
            n_wf = (
                int(wf_count)
                if wf_count is not None
                else (len(wf_list) if isinstance(wf_list, list) else 0)
            )
        except (TypeError, ValueError):
            n_wf = len(wf_list) if isinstance(wf_list, list) else 0
        has_workflows = n_wf > 0
        gap_ci = 0 if has_workflows or ".github/workflows" in names_for_tree else 1
    if tree_names is None:
        gap_tests = None
    else:
        lower_names = {n.lower() for n in tree_names}
        has_test_dir = bool(lower_names & TEST_DIRS)
        has_test_file = any(
            n.endswith((".spec.ts", ".spec.js", ".spec.py", "_test.py"))
            or "_test." in n
            for n in lower_names
        )
        gap_tests = 0 if has_test_dir or has_test_file else 1
    community = (
        rest.get("community") if isinstance(rest.get("community"), dict) else None
    )
    files = community.get("files") if isinstance(community, dict) else {}
    contributing = files.get("contributing") if isinstance(files, dict) else None
    gql_contrib = repo.get("contributing")
    has_contrib = contributing is not None or gql_contrib is not None
    has_docs = any(
        n.lower() in {"docs", "doc"} or n.lower().startswith("contributing")
        for n in names_for_tree
    )
    if has_contrib or has_docs:
        gap_docs = 0
    elif tree_names is None:
        gap_docs = None
    else:
        gap_docs = 1
    health = community.get("health_percentage") if isinstance(community, dict) else None
    try:
        health_f = float(health) if health is not None else None
    except (TypeError, ValueError):
        health_f = None
    headings = [m.group(2).strip() for m in HEADING_RE.finditer(readme_text)]
    install = bool(readme_install(readme_text)) if readme_text else None
    shot = screenshot_only(readme_text) if readme_text else None
    i_open = None
    if isinstance(sample, dict) and sample.get("totalCount") is not None:
        i_open = int(sample["totalCount"])
    elif (
        isinstance(repo.get("issuesOpen"), dict)
        and repo["issuesOpen"].get("totalCount") is not None
    ):
        i_open = int(repo["issuesOpen"]["totalCount"])
    tree_kind = None
    if tree_names:
        tree_kind = "readme_only" if is_readme_only_tree(tree_names) else "has_source"
    n_sample = len(nodes)
    maint_touch = (maint_hits / n_sample) if n_sample else None
    excerpt = readme_text[:README_CHARS] if readme_text else None
    open_blob = "\n".join(open_titles)
    if len(open_blob.encode()) > 2048:
        open_titles = _cap_titles(open_titles, 2048)
    help_blob = "\n".join(help_titles)
    if len(help_blob.encode()) > 2048:
        help_titles = _cap_titles(help_titles, 2048)

    return FeaturesBlob(
        u_issue=len(authors) if open_sample_landed else None,
        u_issue_ext=len(authors_ext) if open_sample_landed else None,
        issue_sample_n=n_sample if open_sample_landed else None,
        i_open=i_open,
        bug_n=bug_n if open_sample_landed else None,
        talk_n=talk_n if open_sample_landed else None,
        usage_closed_n=usage_closed_n if closed_sample_landed else None,
        help_n=help_n if open_sample_landed else None,
        unassigned_help=unassigned_help if open_sample_landed else None,
        repeat_clusters=_repeat_clusters(
            [str(i.get("title") or "") for i in nodes if isinstance(i, dict)]
        )
        if open_sample_landed
        else None,
        maint_touch=maint_touch,
        health_percentage=health_f,
        readme_install=install,
        screenshot_only=shot,
        readme_excerpt=excerpt,
        readme_headings=headings or None,
        gap_ci=gap_ci,
        gap_tests=gap_tests,
        gap_docs=gap_docs,
        gap_tests_scope="root_only" if gap_tests is not None else None,
        tree_kind=tree_kind,
        tree_names=tree_names or None,
        has_workflows=has_workflows,
        help_issue_titles=help_titles or None,
        open_issue_titles=open_titles or None,
        bots_dropped=list(dict.fromkeys(bots)) or None,
        phase="B",
    )


def _label_names(issue: Mapping[str, Any]) -> set[str]:
    labels = issue.get("labels")
    nodes = labels.get("nodes") if isinstance(labels, Mapping) else None
    out: set[str] = set()
    if not isinstance(nodes, list):
        return out
    for node in nodes:
        if isinstance(node, Mapping) and node.get("name"):
            out.add(str(node["name"]).lower())
    return out


def _tokenize(title: str) -> set[str]:
    return {w for w in PUNCT_RE.sub(" ", (title or "").lower()).split() if w}


def _repeat_clusters(titles: Sequence[str]) -> int:
    tokens = [_tokenize(t) for t in titles]
    n = len(tokens)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        if not tokens[i]:
            continue
        for j in range(i + 1, n):
            if not tokens[j]:
                continue
            inter = len(tokens[i] & tokens[j])
            union_n = len(tokens[i] | tokens[j])
            if union_n and inter / union_n >= 0.6:
                union(i, j)
    sizes = Counter(find(i) for i in range(n))
    return sum(1 for size in sizes.values() if size >= 3)


def _cap_titles(titles: list[str], nbytes: int) -> list[str]:
    out: list[str] = []
    used = 0
    for title in titles:
        extra = len(title.encode()) + (1 if out else 0)
        if used + extra > nbytes:
            break
        out.append(title)
        used += extra
    return out


def features_json(blob: FeaturesBlob | None) -> str:
    if blob is None:
        return "{}"
    return json.dumps(
        blob.model_dump(mode="json", exclude_none=True), ensure_ascii=False
    )
