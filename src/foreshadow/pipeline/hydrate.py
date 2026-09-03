from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from foreshadow.clock import Clock
from foreshadow.config import DiscoverySettings
from foreshadow.github.client import GitHubError, graphql_marks_incomplete
from foreshadow.github.queries import HYDRATE_A_NODE, HYDRATE_B_NODE
from foreshadow.github.rest import (
    fetch_closed_pulls,
    fetch_commits,
    fetch_community_profile,
    fetch_contributors,
    fetch_releases,
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
EXT_ASSOC = frozenset({"NONE", "CONTRIBUTOR", "FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR"})
MAINT_ASSOC = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
NEWCOMER_ASSOC = frozenset({"FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR"})
OWNER_TYPES = frozenset({"User", "Organization"})


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
    pool: str | None = None
    query_key: str | None = None


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
    remaining = max(0, max_deep - len(phase))
    if remaining <= 0:
        return phase
    has_pools = any(getattr(c, "pool", None) in {"A", "B", "C"} for c in rest)
    if not has_pools:
        rest.sort(
            key=lambda c: pre_rank_key(c, cfg=cfg, bags=bags, now=now), reverse=True
        )
        for repo in rest:
            if len(phase) >= max_deep:
                break
            phase.append(repo)
            taken.add(nid_of(repo))
        return phase
    seated = _seat_deep_pools(rest, remaining, cfg, bags, now)
    for repo in seated:
        if len(phase) >= max_deep:
            break
        nid = nid_of(repo)
        if nid in taken:
            continue
        phase.append(repo)
        taken.add(nid)
    leftover = [c for c in rest if nid_of(c) not in taken]
    leftover.sort(
        key=lambda c: pre_rank_key(c, cfg=cfg, bags=bags, now=now), reverse=True
    )
    for repo in leftover:
        if len(phase) >= max_deep:
            break
        phase.append(repo)
        taken.add(nid_of(repo))
    return phase


def _scaled_phase_quotas(
    quotas: dict[str, int], remaining: int, total: int
) -> dict[str, int]:
    if remaining <= 0:
        return {key: 0 for key in quotas}
    if remaining >= total:
        return dict(quotas)
    out = {key: int(quotas[key] * remaining / max(total, 1)) for key in quotas}
    leftover = remaining - sum(out.values())
    for pool in ("A", "B", "C"):
        if leftover <= 0:
            break
        if quotas.get(pool, 0) <= 0:
            continue
        out[pool] = out.get(pool, 0) + 1
        leftover -= 1
    return out


def _seat_deep_pools(
    rest: Sequence[Any],
    remaining: int,
    cfg: DiscoverySettings,
    bags: Sequence[DirectionBag],
    now: datetime | date,
) -> list[Any]:
    """Seat each pool up to its own quota. No raw-star sort.

    Unused quota is not taken from a pool that still has unseated hits.
    Leftover seats (underfilled pools) are filled later by pre_rank.
    """
    quotas = _scaled_phase_quotas(
        {
            "A": cfg.phase_b_pool_a,
            "B": cfg.phase_b_pool_b,
            "C": cfg.phase_b_pool_c,
        },
        remaining,
        max(cfg.max_deep_hydrate, remaining),
    )
    by_pool: dict[str, list[Any]] = {"A": [], "B": [], "C": []}
    for repo in rest:
        pool = getattr(repo, "pool", None)
        if pool in by_pool:
            by_pool[pool].append(repo)
    floor = max(0, int(cfg.phase_b_per_query_floor))
    out: list[Any] = []
    for pool in ("A", "B", "C"):
        group = by_pool[pool]
        group.sort(
            key=lambda c: pre_rank_key(c, cfg=cfg, bags=bags, now=now), reverse=True
        )
        out.extend(_round_robin_query_key(group, int(quotas.get(pool, 0)), floor))
    return out


def _round_robin_query_key(
    repos: Sequence[Any], quota: int, per_query_floor: int
) -> list[Any]:
    if quota <= 0 or not repos:
        return []
    groups: dict[str, list[Any]] = {}
    order: list[str] = []
    for repo in repos:
        key = str(getattr(repo, "query_key", None) or "_")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(repo)
    taken: set[str] = set()
    out: list[Any] = []

    def nid(repo: Any) -> str:
        return str(_get(repo, "node_id", "id", default="") or "")

    floor = max(0, per_query_floor)
    for key in order:
        for repo in groups[key][:floor]:
            if len(out) >= quota:
                return out
            ident = nid(repo)
            if ident in taken:
                continue
            taken.add(ident)
            out.append(repo)
    progressed = True
    while progressed and len(out) < quota:
        progressed = False
        for key in order:
            for repo in groups[key]:
                ident = nid(repo)
                if ident in taken:
                    continue
                taken.add(ident)
                out.append(repo)
                progressed = True
                break
            if len(out) >= quota:
                break
    return out


def medium_shortlist(
    candidates: Sequence[Any],
    already: Sequence[Any],
    *,
    cfg: DiscoverySettings | None = None,
    bags: Sequence[DirectionBag] | None = None,
    now: datetime | date | None = None,
    exclude_forks: bool = True,
) -> list[Any]:
    """Cheaper REST tier. Does not consume Phase B GraphQL issue samples."""
    cfg = cfg or DiscoverySettings()
    bags = list(bags) if bags is not None else load_direction_bags()
    now = now or datetime.now(UTC)
    taken = {str(_get(c, "node_id", "id", default="") or "") for c in already}

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

    rest = [
        c
        for c in candidates
        if not dropped(c)
        and str(_get(c, "node_id", "id", default="") or "") not in taken
    ]
    cap = int(cfg.max_medium_hydrate)
    if cap <= 0 or not rest:
        return []
    if not any(getattr(c, "pool", None) in {"A", "B", "C"} for c in rest):
        rest.sort(
            key=lambda c: pre_rank_key(c, cfg=cfg, bags=bags, now=now), reverse=True
        )
        return rest[:cap]
    cfg_med = cfg.model_copy(
        update={
            "phase_b_pool_a": cfg.medium_pool_a,
            "phase_b_pool_b": cfg.medium_pool_b,
            "phase_b_pool_c": cfg.medium_pool_c,
            "max_deep_hydrate": cap,
        }
    )
    seated = _seat_deep_pools(rest, cap, cfg_med, bags, now)
    out: list[Any] = []
    seen: set[str] = set()
    for repo in seated:
        ident = str(_get(repo, "node_id", "id", default="") or "")
        if ident in seen:
            continue
        seen.add(ident)
        out.append(repo)
        if len(out) >= cap:
            return out
    leftover = [
        c for c in rest if str(_get(c, "node_id", "id", default="") or "") not in seen
    ]
    leftover.sort(
        key=lambda c: pre_rank_key(c, cfg=cfg, bags=bags, now=now), reverse=True
    )
    for repo in leftover:
        if len(out) >= cap:
            break
        ident = str(_get(repo, "node_id", "id", default="") or "")
        if ident in seen:
            continue
        seen.add(ident)
        out.append(repo)
    return out[:cap]


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


def hydrate_a_many(
    client: Any, node_ids: Sequence[str], *, force: bool = False
) -> dict[str, tuple[dict | None, GitHubError | None]]:
    """Bounded concurrent HydrateANode. Fake clients stay serial."""
    ids = [str(n) for n in node_ids]
    workers = 1
    settings = getattr(client, "settings", None)
    if (
        type(client).__name__ == "GitHubClient"
        and settings is not None
        and len(ids) > 1
    ):
        workers = max(1, min(int(getattr(settings, "hydrate_concurrency", 1) or 1), 8))
    if workers <= 1:
        return {nid: hydrate_a_node(client, nid, force=force) for nid in ids}
    out: dict[str, tuple[dict | None, GitHubError | None]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(hydrate_a_node, client, nid, force=force): nid for nid in ids
        }
        for fut in as_completed(futs):
            out[futs[fut]] = fut.result()
    return out


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
    fetched = hydrate_a_many(client, list(identity_ids), force=force)
    for nid in identity_ids:
        row = conn.execute(
            "SELECT id, node_id, full_name, status FROM repos WHERE node_id=?",
            (nid,),
        ).fetchone()
        body, err = fetched.get(nid, (None, None))
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
        "releases": None,
    }
    try:
        out["contributors"] = fetch_contributors(client, owner, name)
    except GitHubError:
        pass
    try:
        out["commits"] = fetch_commits(
            client, owner, name, clock.now() - timedelta(days=30), max_pages=1
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
    try:
        out["releases"] = fetch_releases(client, owner, name)
    except GitHubError:
        out["releases"] = None
    return out


def hydrate_medium_rest(
    client: Any,
    owner: str,
    name: str,
    clock: Clock,
) -> dict[str, Any]:
    """Contributors + recent commits + releases + one closed-PR page."""
    out: dict[str, Any] = {
        "contributors": None,
        "commits": None,
        "releases": None,
        "pulls": None,
    }
    try:
        out["contributors"] = fetch_contributors(client, owner, name)
    except GitHubError:
        pass
    try:
        out["commits"] = fetch_commits(
            client, owner, name, clock.now() - timedelta(days=30), max_pages=1
        )
    except GitHubError:
        pass
    try:
        out["releases"] = fetch_releases(client, owner, name)
    except GitHubError:
        pass
    try:
        out["pulls"] = fetch_closed_pulls(client, owner, name)
    except GitHubError:
        out["pulls"] = None
    return out


def activity_from_commits(
    commits: Sequence[Mapping[str, Any]] | None, now: datetime
) -> dict[str, int | None]:
    """Commit *counts* for activity evidence. Never star growth / windows.v7."""
    if commits is None:
        return {
            "commits_7d": None,
            "commits_30d": None,
            "recent_contributors_7d": None,
        }
    cutoff7 = now - timedelta(days=7)
    n7 = 0
    authors7: set[str] = set()
    for row in commits:
        if not isinstance(row, Mapping):
            continue
        dt = _commit_datetime(row)
        if dt is None:
            continue
        if dt >= cutoff7:
            n7 += 1
            login = None
            author = row.get("author")
            if isinstance(author, Mapping):
                login = author.get("login")
            atype = author.get("type") if isinstance(author, Mapping) else None
            if login and not is_bot(str(login), atype):
                authors7.add(str(login).lower())
    return {
        "commits_7d": n7,
        "commits_30d": len([c for c in commits if isinstance(c, Mapping)]),
        "recent_contributors_7d": len(authors7),
    }


def _commit_datetime(row: Mapping[str, Any]) -> datetime | None:
    commit = row.get("commit") if isinstance(row.get("commit"), Mapping) else None
    if commit:
        for key in ("author", "committer"):
            block = commit.get(key)
            if isinstance(block, Mapping) and block.get("date"):
                parsed = parse_dt(block.get("date"))
                if parsed is not None:
                    return parsed
    return None


def releases_30d(rows: Sequence[Mapping[str, Any]] | None, now: datetime) -> int | None:
    if rows is None:
        return None
    cutoff = now - timedelta(days=30)
    n = 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        dt = parse_dt(row.get("published_at") or row.get("created_at"))
        if dt is not None and dt >= cutoff:
            n += 1
    return n


def classify_data_completeness(
    feat: FeaturesBlob | None,
    contributor_count: int | None,
) -> Literal["high", "medium", "low"]:
    """Describes available features. Does not change Opportunity."""
    if feat is None:
        return "low"
    has_c = contributor_count is not None
    has_issues = feat.issue_sample_n is not None
    has_tree = feat.tree_names is not None
    has_maint = feat.maint_touch is not None
    has_pr = feat.pr_merged_sample_n is not None
    deep_bits = sum([has_c, has_issues, has_tree, has_maint or has_pr])
    if deep_bits >= 3:
        return "high"
    if has_c or feat.commits_30d is not None or feat.phase in {"B", "M"}:
        return "medium"
    return "low"


def build_features_blob(
    repo: dict[str, Any],
    rest: Mapping[str, Any],
    *,
    now: datetime | None = None,
    contributor_count: int | None = None,
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
    response_hours: list[float] = []
    for issue in nodes:
        if not isinstance(issue, dict):
            continue
        title = str(issue.get("title") or "")
        number = issue.get("number")
        open_titles.append(f"#{number} {title}" if number is not None else title)
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
        issue_created = parse_dt(issue.get("createdAt"))
        first_maint_at: datetime | None = None
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
                    c_at = parse_dt(cmt.get("createdAt"))
                    if first_maint_at is None and c_at is not None:
                        first_maint_at = c_at
        if talked:
            talk_n += 1
        if maint:
            maint_hits += 1
        if issue_created is not None and first_maint_at is not None:
            hours = (first_maint_at - issue_created).total_seconds() / 3600.0
            if hours >= 0:
                response_hours.append(hours)
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
    maint_hours = None
    if response_hours:
        maint_hours = sum(response_hours) / len(response_hours)
    pr_n, pr_ext, pr_rate, pr_rev, pr_rev_rate = _pr_acceptance(repo)
    now_dt = now or datetime.now(UTC)
    activity = activity_from_commits(
        rest.get("commits") if isinstance(rest.get("commits"), list) else None,
        now_dt,
    )
    rel_n = releases_30d(
        rest.get("releases") if isinstance(rest.get("releases"), list) else None,
        now_dt,
    )
    excerpt = readme_text[:README_CHARS] if readme_text else None
    open_blob = "\n".join(open_titles)
    if len(open_blob.encode()) > 2048:
        open_titles = _cap_titles(open_titles, 2048)
    help_blob = "\n".join(help_titles)
    if len(help_blob.encode()) > 2048:
        help_titles = _cap_titles(help_titles, 2048)
    owner_intel = _creator_intel(repo, now_dt)
    pr_intel = _pr_openness(repo)
    summary_intel = _summary_intel(repo, excerpt, now_dt)

    blob = FeaturesBlob(
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
        pr_merged_sample_n=pr_n,
        pr_external_merged_n=pr_ext,
        pr_accept_rate=pr_rate,
        pr_reviewed_n=pr_rev,
        pr_review_rate=pr_rev_rate,
        maint_first_response_hours=maint_hours,
        commits_7d=activity["commits_7d"],
        commits_30d=activity["commits_30d"],
        recent_contributors_7d=activity["recent_contributors_7d"],
        releases_30d=rel_n,
        issues_created_7d=None,
        issues_created_30d=None,
        prs_created_7d=None,
        prs_created_30d=None,
        data_completeness=None,
        owner_type=owner_intel["owner_type"],
        owner_login=owner_intel["owner_login"],
        owner_created_at=owner_intel["owner_created_at"],
        creator_repo_n=owner_intel["creator_repo_n"],
        creator_success_n=owner_intel["creator_success_n"],
        creator_abandoned_n=owner_intel["creator_abandoned_n"],
        creator_longest_maintained_days=owner_intel["creator_longest_maintained_days"],
        creator_recent_push_n=owner_intel["creator_recent_push_n"],
        creator_release_n=owner_intel["creator_release_n"],
        pr_closed_sample_n=pr_intel["pr_closed_sample_n"],
        pr_external_closed_n=pr_intel["pr_external_closed_n"],
        pr_external_merged_closed_n=pr_intel["pr_external_merged_closed_n"],
        pr_newcomer_closed_n=pr_intel["pr_newcomer_closed_n"],
        pr_newcomer_merged_n=pr_intel["pr_newcomer_merged_n"],
        pr_ext_first_response_hours=pr_intel["pr_ext_first_response_hours"],
        pr_ext_merge_hours=pr_intel["pr_ext_merge_hours"],
        pr_ignored_ext_n=None,
        pr_sample_start=pr_intel["pr_sample_start"],
        pr_sample_end=pr_intel["pr_sample_end"],
        pr_sample_truncated=pr_intel["pr_sample_truncated"],
        summary=summary_intel["summary"],
        summary_at=summary_intel["summary_at"],
        summary_source_sha=summary_intel["summary_source_sha"],
        star_trust=None,
    )
    blob.data_completeness = classify_data_completeness(blob, contributor_count)
    return blob


def build_medium_features_blob(
    rest: Mapping[str, Any],
    *,
    now: datetime | None = None,
    contributor_count: int | None = None,
) -> FeaturesBlob:
    now_dt = now or datetime.now(UTC)
    commits = rest.get("commits") if isinstance(rest.get("commits"), list) else None
    activity = activity_from_commits(commits, now_dt)
    rel_n = releases_30d(
        rest.get("releases") if isinstance(rest.get("releases"), list) else None,
        now_dt,
    )
    pr_n, pr_ext, pr_rate, pr_rev, pr_rev_rate = _pr_acceptance_from_pulls(
        rest.get("pulls")
    )
    blob = FeaturesBlob(
        phase="M",
        commits_7d=activity["commits_7d"],
        commits_30d=activity["commits_30d"],
        recent_contributors_7d=activity["recent_contributors_7d"],
        releases_30d=rel_n,
        issues_created_7d=None,
        issues_created_30d=None,
        prs_created_7d=None,
        prs_created_30d=None,
        pr_merged_sample_n=pr_n,
        pr_external_merged_n=pr_ext,
        pr_accept_rate=pr_rate,
        pr_reviewed_n=pr_rev,
        pr_review_rate=pr_rev_rate,
        owner_type=None,
        owner_login=None,
        owner_created_at=None,
        creator_repo_n=None,
        creator_success_n=None,
        creator_abandoned_n=None,
        creator_longest_maintained_days=None,
        creator_recent_push_n=None,
        creator_release_n=None,
        pr_closed_sample_n=None,
        pr_external_closed_n=None,
        pr_external_merged_closed_n=None,
        pr_newcomer_closed_n=None,
        pr_newcomer_merged_n=None,
        pr_ext_first_response_hours=None,
        pr_ext_merge_hours=None,
        pr_ignored_ext_n=None,
        summary=None,
        summary_at=None,
        summary_source_sha=None,
        star_trust=None,
    )
    blob.data_completeness = classify_data_completeness(blob, contributor_count)
    return blob


def _empty_owner_intel() -> dict[str, Any]:
    return {
        "owner_type": None,
        "owner_login": None,
        "owner_created_at": None,
        "creator_repo_n": None,
        "creator_success_n": None,
        "creator_abandoned_n": None,
        "creator_longest_maintained_days": None,
        "creator_recent_push_n": None,
        "creator_release_n": None,
    }


def _empty_pr_openness() -> dict[str, Any]:
    return {
        "pr_closed_sample_n": None,
        "pr_external_closed_n": None,
        "pr_external_merged_closed_n": None,
        "pr_newcomer_closed_n": None,
        "pr_newcomer_merged_n": None,
        "pr_ext_first_response_hours": None,
        "pr_ext_merge_hours": None,
        "pr_ignored_ext_n": None,
        "pr_sample_start": None,
        "pr_sample_end": None,
        "pr_sample_truncated": None,
    }


def _empty_summary_intel() -> dict[str, Any]:
    return {"summary": None, "summary_at": None, "summary_source_sha": None}


def _owner_identity(owner: Mapping[str, Any]) -> dict[str, Any]:
    typename = owner.get("__typename")
    login = owner.get("login")
    created = owner.get("createdAt")
    return {
        "owner_type": typename if typename in OWNER_TYPES else None,
        "owner_login": str(login) if login else None,
        "owner_created_at": str(created) if created else None,
    }


def _creator_intel(repo: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    owner = repo.get("owner")
    if not isinstance(owner, Mapping):
        return _empty_owner_intel()
    current = str(repo.get("nameWithOwner") or "")
    stats = _creator_stats_from_module(owner, current_nwo=current, now=now)
    if stats is not None:
        out = _empty_owner_intel()
        out.update(_owner_identity(owner))
        for key in out:
            if key in stats:
                out[key] = stats[key]
        return out
    return _creator_from_owner(owner, current_nwo=current, now=now)


def _creator_stats_from_module(
    owner: Mapping[str, Any], *, current_nwo: str, now: datetime
) -> dict[str, Any] | None:
    try:
        from foreshadow.pipeline import creator as creator_mod
    except ImportError:
        return None
    for name in ("compute_creator_stats", "creator_stats", "from_owner"):
        fn = getattr(creator_mod, name, None)
        if not callable(fn):
            continue
        try:
            result = fn(owner, current_nwo=current_nwo, now=now)
        except TypeError:
            try:
                result = fn(owner, current_nwo, now)
            except TypeError:
                continue
        if isinstance(result, Mapping):
            return dict(result)
    return None


def _creator_from_owner(
    owner: Mapping[str, Any], *, current_nwo: str, now: datetime
) -> dict[str, Any]:
    """Owner sample stats. Never stores star or follower sums."""
    out = _empty_owner_intel()
    out.update(_owner_identity(owner))
    repos = owner.get("repositories")
    nodes = repos.get("nodes") if isinstance(repos, Mapping) else None
    if not isinstance(nodes, list):
        return out
    sample: list[Mapping[str, Any]] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        nwo = str(node.get("nameWithOwner") or "")
        if current_nwo and nwo == current_nwo:
            continue
        sample.append(node)
    success = 0
    abandoned = 0
    recent = 0
    released = 0
    longest: int | None = None
    for node in sample:
        created = parse_dt(node.get("createdAt"))
        pushed = parse_dt(node.get("pushedAt"))
        age = None if created is None else (now.date() - created.date()).days
        pushed_age = None if pushed is None else (now.date() - pushed.date()).days
        is_fork = bool(node.get("isFork"))
        is_archived = bool(node.get("isArchived"))
        rel = node.get("releases")
        try:
            n_rel = int(rel.get("totalCount") or 0) if isinstance(rel, Mapping) else 0
        except (TypeError, ValueError):
            n_rel = 0
        if n_rel >= 1:
            released += 1
        if pushed_age is not None and pushed_age <= 90:
            recent += 1
        recent_or_released = (pushed_age is not None and pushed_age <= 90) or n_rel >= 1
        if (
            not is_fork
            and age is not None
            and age >= 180
            and not is_archived
            and recent_or_released
        ):
            success += 1
        if (
            age is not None
            and age >= 180
            and pushed_age is not None
            and pushed_age > 365
        ):
            abandoned += 1
        if created is not None:
            end = pushed or now
            span = (end.date() - created.date()).days
            if span >= 0 and (longest is None or span > longest):
                longest = span
    out["creator_repo_n"] = len(sample)
    out["creator_success_n"] = success
    out["creator_abandoned_n"] = abandoned
    out["creator_longest_maintained_days"] = longest
    out["creator_recent_push_n"] = recent
    out["creator_release_n"] = released
    return out


def _pr_openness(repo: Mapping[str, Any]) -> dict[str, Any]:
    merged_raw = repo.get("prsMerged")
    closed_raw = repo.get("prsClosed")
    merged_nodes = merged_raw.get("nodes") if isinstance(merged_raw, Mapping) else None
    closed_nodes = closed_raw.get("nodes") if isinstance(closed_raw, Mapping) else None
    if not isinstance(merged_nodes, list) or not isinstance(closed_nodes, list):
        return _empty_pr_openness()
    combined: list[tuple[bool, Mapping[str, Any]]] = []
    for pr in merged_nodes:
        if isinstance(pr, Mapping):
            combined.append((True, pr))
    for pr in closed_nodes:
        if isinstance(pr, Mapping) and not pr.get("mergedAt"):
            combined.append((False, pr))
    ext_closed = 0
    ext_merged = 0
    newcomer_closed = 0
    newcomer_merged = 0
    resp_hours: list[float] = []
    merge_hours: list[float] = []
    created_days: list[str] = []
    for merged, pr in combined:
        created = pr.get("createdAt") or pr.get("created_at")
        if created:
            created_days.append(str(created)[:10])
        if _pr_is_bot(pr):
            continue
        assoc = str(pr.get("authorAssociation") or "")
        is_ext = assoc in EXT_ASSOC
        is_new = assoc in NEWCOMER_ASSOC
        if is_ext:
            ext_closed += 1
            if merged:
                ext_merged += 1
            hours = _first_maint_response_hours(pr)
            if hours is not None:
                resp_hours.append(hours)
            if merged:
                mh = _pr_merge_hours(pr)
                if mh is not None:
                    merge_hours.append(mh)
        if is_new:
            newcomer_closed += 1
            if merged:
                newcomer_merged += 1
    return {
        "pr_closed_sample_n": len(combined),
        "pr_external_closed_n": ext_closed,
        "pr_external_merged_closed_n": ext_merged,
        "pr_newcomer_closed_n": newcomer_closed,
        "pr_newcomer_merged_n": newcomer_merged,
        "pr_ext_first_response_hours": _median(resp_hours),
        "pr_ext_merge_hours": _median(merge_hours),
        "pr_ignored_ext_n": None,
        "pr_sample_start": min(created_days) if created_days else None,
        "pr_sample_end": max(created_days) if created_days else None,
        "pr_sample_truncated": len(merged_nodes) >= 20 or len(closed_nodes) >= 30,
    }


def _pr_is_bot(pr: Mapping[str, Any]) -> bool:
    from foreshadow.pipeline.openness import BOT_LOGINS, is_external_author

    author = pr.get("author") if isinstance(pr.get("author"), Mapping) else {}
    login = author.get("login") if isinstance(author, Mapping) else None
    typ = author.get("type") if isinstance(author, Mapping) else None
    if is_bot(login, typ):
        return True
    if isinstance(login, str) and (
        login.endswith("[bot]") or login.lower().removesuffix("[bot]") in BOT_LOGINS
    ):
        return True
    assoc = str(pr.get("authorAssociation") or "")
    return assoc in EXT_ASSOC and not is_external_author(assoc, login, typ)


def _comment_nodes(pr: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    comments = pr.get("comments") if isinstance(pr.get("comments"), Mapping) else {}
    nodes = comments.get("nodes") if isinstance(comments, Mapping) else None
    if not isinstance(nodes, list):
        return []
    return [cmt for cmt in nodes if isinstance(cmt, Mapping)]


def _first_maint_response_hours(pr: Mapping[str, Any]) -> float | None:
    created = parse_dt(pr.get("createdAt"))
    if created is None:
        return None
    comments = _comment_nodes(pr)
    if not comments:
        return None
    first_maint: datetime | None = None
    for cmt in comments:
        if str(cmt.get("authorAssociation") or "") not in MAINT_ASSOC:
            continue
        c_at = parse_dt(cmt.get("createdAt"))
        if c_at is None:
            continue
        if first_maint is None or c_at < first_maint:
            first_maint = c_at
    if first_maint is None:
        return None
    hours = (first_maint - created).total_seconds() / 3600.0
    if hours < 0:
        return None
    return hours


def _pr_merge_hours(pr: Mapping[str, Any]) -> float | None:
    created = parse_dt(pr.get("createdAt"))
    merged_at = parse_dt(pr.get("mergedAt"))
    if created is None or merged_at is None:
        return None
    hours = (merged_at - created).total_seconds() / 3600.0
    if hours < 0:
        return None
    return hours


def _is_ignored_ext_pr(pr: Mapping[str, Any]) -> bool:
    reviews = pr.get("reviews") if isinstance(pr.get("reviews"), Mapping) else {}
    try:
        rc = int(reviews.get("totalCount") or 0) if isinstance(reviews, Mapping) else 0
    except (TypeError, ValueError):
        rc = 0
    if rc > 0:
        return False
    for cmt in _comment_nodes(pr):
        if str(cmt.get("authorAssociation") or "") in MAINT_ASSOC:
            return False
    return True


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _repo_topics(repo: Mapping[str, Any]) -> list[str]:
    raw = repo.get("repositoryTopics") or {}
    nodes = raw.get("nodes") if isinstance(raw, Mapping) else None
    out: list[str] = []
    if not isinstance(nodes, list):
        return out
    for node in nodes:
        if isinstance(node, Mapping) and isinstance(node.get("topic"), Mapping):
            name = node["topic"].get("name")
            if name:
                out.append(str(name))
    return out


def _default_branch_oid(repo: Mapping[str, Any]) -> str | None:
    ref = repo.get("defaultBranchRef")
    if not isinstance(ref, Mapping):
        return None
    target = ref.get("target")
    if not isinstance(target, Mapping):
        return None
    oid = target.get("oid")
    return str(oid) if oid else None


def _summary_intel(
    repo: Mapping[str, Any], excerpt: str | None, now: datetime
) -> dict[str, Any]:
    try:
        from foreshadow.pipeline.summary import summarize_project
    except ImportError:
        return _empty_summary_intel()
    oid = _default_branch_oid(repo)
    result = summarize_project(
        repo.get("description"), excerpt, _repo_topics(repo), oid
    )
    if result is None:
        return _empty_summary_intel()
    if isinstance(result, Mapping):
        summary = result.get("summary") or result.get("text")
        if not summary:
            return _empty_summary_intel()
        at = result.get("summary_at") or now.isoformat()
        sha = result.get("summary_source_sha") or result.get("source_sha") or oid
        return {
            "summary": str(summary),
            "summary_at": str(at),
            "summary_source_sha": str(sha) if sha else None,
        }
    text = getattr(result, "summary", None) or getattr(result, "text", None)
    if text:
        at = (
            getattr(result, "summary_at", None)
            or getattr(result, "at", None)
            or now.isoformat()
        )
        sha = (
            getattr(result, "summary_source_sha", None)
            or getattr(result, "source_sha", None)
            or oid
        )
        return {
            "summary": str(text),
            "summary_at": str(at),
            "summary_source_sha": str(sha) if sha else None,
        }
    raw = str(result).strip()
    if not raw:
        return _empty_summary_intel()
    return {
        "summary": raw,
        "summary_at": now.isoformat(),
        "summary_source_sha": oid,
    }


def _pr_acceptance(
    repo: Mapping[str, Any],
) -> tuple[int | None, int | None, float | None, int | None, float | None]:
    raw = repo.get("prsMerged")
    nodes = raw.get("nodes") if isinstance(raw, dict) else None
    if not isinstance(nodes, list):
        return None, None, None, None, None
    n = len(nodes)
    if n == 0:
        return 0, None, None, None, None
    ext = 0
    reviewed = 0
    for pr in nodes:
        if not isinstance(pr, dict):
            continue
        if str(pr.get("authorAssociation") or "") in EXT_ASSOC:
            ext += 1
        reviews = pr.get("reviews") if isinstance(pr.get("reviews"), dict) else {}
        try:
            rc = int(reviews.get("totalCount") or 0)
        except (TypeError, ValueError):
            rc = 0
        if rc > 0:
            reviewed += 1
    return n, ext, ext / n, reviewed, reviewed / n


def _pr_acceptance_from_pulls(
    rows: object,
) -> tuple[int | None, int | None, float | None, int | None, float | None]:
    """REST closed-PR page. Review rate stays UNKNOWN (no extra review calls)."""
    if not isinstance(rows, list):
        return None, None, None, None, None
    if not rows:
        return 0, None, None, None, None
    merged: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if row.get("merged_at") or row.get("merged") is True:
            merged.append(row)
    n = len(merged)
    if n == 0:
        return 0, None, None, None, None
    ext = 0
    for pr in merged:
        assoc = str(pr.get("author_association") or pr.get("authorAssociation") or "")
        if assoc in EXT_ASSOC or assoc in {"FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR"}:
            ext += 1
    return n, ext, ext / n, None, None


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
