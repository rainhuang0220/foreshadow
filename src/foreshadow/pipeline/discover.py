from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from foreshadow.clock import Clock
from foreshadow.config import DiscoverySettings, Settings
from foreshadow.github.client import GitHubError, graphql_marks_incomplete
from foreshadow.github.queries import SEARCH_REPOS
from foreshadow.pipeline.direction import is_keyword_stuffing, load_direction_bags
from foreshadow.pipeline.hydrate import (
    HydratedRepo,
    apply_identity,
    build_features_blob,
    census_contributors,
    extract_repo,
    features_json,
    from_graphql,
    hydrate_a_node,
    hydrate_b_node,
    hydrate_phase_b_rest,
    insert_hit,
    phase_b_shortlist,
    unique_committers_30d,
    update_repo_from_graphql,
    upsert_repo_from_graphql,
)
from foreshadow.pipeline.snapshot import payload_from_graphql, upsert_snapshot

# Pool A/B/C recall. Stars are query bounds, never a fill target or pre-rank key.
# No sort:stars. Magnet product names are forbidden (see MAGNET_TERMS).
#
# GitHub search returns 0 hits (no error) for illegal OR mixes:
#   topic:X OR topic:Y
#   topic:X OR "quoted phrase"
#   (bare OR bare OR "quoted") combined with stars:/pushed:/sort:
# Keep one topic: per query, or unquoted token OR, never both.
SEARCH_QUERY_TEMPLATES: dict[str, str] = {
    "A_mcp": (
        "is:public archived:false stars:{early} pushed:>{pushed45} sort:updated "
        "topic:mcp"
    ),
    "A_agent": (
        "is:public archived:false stars:{early} pushed:>{pushed45} sort:updated "
        "topic:agents"
    ),
    "A_memory": (
        "is:public archived:false stars:{early} pushed:>{pushed45} sort:updated "
        "topic:memory"
    ),
    "A_eval": (
        "is:public archived:false stars:{early} pushed:>{pushed45} sort:updated "
        "(evals OR evaluation)"
    ),
    "A_help": (
        "is:public archived:false stars:{early} pushed:>{pushed45} sort:updated "
        "help-wanted-issues:>0 (mcp OR agent OR llm)"
    ),
    "B_mcp": (
        "is:public archived:false stars:{rising} pushed:>{pushed14} sort:updated "
        "topic:mcp"
    ),
    "B_agent": (
        "is:public archived:false stars:{rising} pushed:>{pushed14} sort:updated "
        "topic:agents"
    ),
    "B_runtime": (
        "is:public archived:false stars:{rising} pushed:>{pushed14} sort:updated "
        "(gguf OR mlx OR candle)"
    ),
    "B_systems": (
        "is:public archived:false stars:{rising} pushed:>{pushed14} sort:updated "
        "language:Rust (embedded OR riscv OR osdev)"
    ),
    "B_help": (
        "is:public archived:false stars:{rising} pushed:>{pushed45} sort:updated "
        "help-wanted-issues:>0 (mcp OR agent)"
    ),
    "C_mcp": (
        "is:public archived:false created:>{created180} pushed:>{pushed45} "
        "sort:updated topic:mcp"
    ),
    "C_agent": (
        "is:public archived:false created:>{created180} pushed:>{pushed45} "
        "sort:updated (agent framework OR mcp server)"
    ),
    "C_memory": (
        "is:public archived:false created:>{created180} pushed:>{pushed45} "
        "sort:updated topic:memory"
    ),
    "C_bench": (
        "is:public archived:false created:>{created180} pushed:>{pushed45} "
        "sort:updated topic:benchmark"
    ),
}

MAGNET_TERMS = (
    "llama.cpp",
    "ollama",
    "vllm",
    "cuda",
    "rocm",
    "tensor rt",
)
POOL_ORDER = ("A", "B", "C")
_JUNK_NAME = ("awesome-", "cheatsheet", "chatgpt-wrapper")


@dataclass
class SearchHit:
    node_id: str
    full_name: str
    query_key: str
    pool: str = "B"
    database_id: int | None = None
    url: str | None = None
    description: str | None = None
    created_at: str | None = None
    pushed_at: str | None = None
    is_fork: bool = False
    is_archived: bool = False
    is_disabled: bool = False
    is_empty: bool = False
    is_mirror: bool = False
    has_issues: bool | None = None
    stargazer_count: int = 0
    fork_count: int = 0
    language: str | None = None
    license_spdx: str | None = None
    topics: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass
class WatchlistEntry:
    node_id: str
    repo_id: int
    full_name: str
    action: str
    created_at: str


@dataclass
class CappedCandidate:
    node_id: str
    full_name: str
    origin: str
    query_key: str | None = None
    pool: str | None = None
    action: str | None = None
    hit: SearchHit | None = None


@dataclass
class CapResult:
    candidates: list[CappedCandidate]
    watchlist_truncated: bool
    search_capped: bool

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)


@dataclass
class DiscoveryResult:
    run_id: int
    candidate_count: int
    phase_a_ids: list[str]
    phase_b_ids: list[str]
    identity_ids: set[str]
    collisions: set[str]
    source_health: dict[str, Any]
    search_hits: list[SearchHit]
    capped: CapResult


def pool_of(query_key: str | None) -> str:
    key = query_key or ""
    if key.startswith("A_"):
        return "A"
    if key.startswith("C_"):
        return "C"
    return "B"


def boolean_operator_count(query: str) -> int:
    tokens = query.replace("(", " ").replace(")", " ").split()
    return sum(1 for tok in tokens if tok in {"AND", "OR", "NOT"})


def lightweight_keep(hit: SearchHit) -> bool:
    """Post-union quality filter. Underfill is preferred over junk.

    Pool C always goes through this gate. Empty seats beat stuffed wrappers.
    """
    if hit.is_fork or hit.is_archived or hit.is_disabled or hit.is_empty:
        return False
    if hit.has_issues is False:
        return False
    name = (hit.full_name or "").split("/", 1)[-1].lower()
    desc = (hit.description or "").strip()
    if any(junk in name or junk in desc.lower() for junk in _JUNK_NAME):
        return False
    if is_keyword_stuffing(desc):
        return False
    has_topics = bool(hit.topics)
    if not desc and not has_topics:
        return False
    if hit.pool == "C":
        has_attention = hit.stargazer_count >= 1 or hit.fork_count >= 1
        return (
            len(desc) >= 20
            and (has_topics or hit.fork_count >= 1)
            and has_attention
        )
    if hit.pool == "A":
        return hit.fork_count >= 1 or has_topics or hit.query_key == "A_help"
    return True


def is_degraded(health: dict[str, Any]) -> bool:
    return bool(
        health.get("search_truncated")
        or health.get("budget_abort")
        or int(health.get("hydrate_failed") or 0) > 0
        or health.get("watchlist_truncated")
    )


def search_candidates(
    client: Any,
    settings: Settings,
    today: date,
    *,
    force: bool = False,
    health: dict[str, Any] | None = None,
) -> list[SearchHit]:
    disc = settings.discovery
    subs = {
        "star_min": disc.star_min,
        "star_max": disc.star_max,
        "early": f"{disc.early_star_min}..{disc.early_star_max}",
        "rising": f"{disc.rising_star_min}..{disc.rising_star_max}",
        "pushed45": (today - timedelta(days=disc.pushed_within_days)).isoformat(),
        "created180": (today - timedelta(days=180)).isoformat(),
        "pushed14": (today - timedelta(days=14)).isoformat(),
    }
    hits_by_id: dict[str, SearchHit] = {}
    truncated = False
    budget_abort = False
    per_page = disc.per_page
    pool_rank = {name: i for i, name in enumerate(POOL_ORDER)}
    for key, tmpl in SEARCH_QUERY_TEMPLATES.items():
        if getattr(client, "should_stop", lambda: False)():
            budget_abort = True
            break
        q = tmpl.format(**subs)
        nodes: list[dict[str, Any]] = []
        count = 0
        try:
            body = client.graphql(SEARCH_REPOS, {"q": q, "n": per_page}, force=force)
            nodes, count = _parse_search_graphql(body)
        except GitHubError as exc:
            if exc.reason == "budget":
                budget_abort = True
                break
            nodes, count = _search_rest(client, q, per_page)
        except TypeError:
            body = client.graphql(SEARCH_REPOS, {"q": q, "n": per_page})
            nodes, count = _parse_search_graphql(body)
        if count > per_page:
            truncated = True
        for node in nodes:
            hit = _hit_from_graphql(node, key)
            if hit is None:
                continue
            if disc.exclude_forks and hit.is_fork:
                continue
            if disc.exclude_archived and hit.is_archived:
                continue
            if not lightweight_keep(hit):
                continue
            prev = hits_by_id.get(hit.node_id)
            if prev is None or pool_rank.get(hit.pool, 9) < pool_rank.get(prev.pool, 9):
                hits_by_id[hit.node_id] = hit
    if health is not None:
        health["search_truncated"] = truncated
        if budget_abort:
            health["budget_abort"] = True
    return list(hits_by_id.values())


def _parse_search_graphql(body: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    data = body.get("data") if isinstance(body, dict) else None
    search = data.get("search") if isinstance(data, dict) else None
    if not isinstance(search, dict):
        return [], 0
    nodes = search.get("nodes") or []
    if not isinstance(nodes, list):
        nodes = []
    try:
        count = int(search.get("repositoryCount") or 0)
    except (TypeError, ValueError):
        count = len(nodes)
    return [n for n in nodes if isinstance(n, dict)], count


def _search_rest(
    client: Any, q: str, per_page: int
) -> tuple[list[dict[str, Any]], int]:
    try:
        resp = client.get("/search/repositories", params={"q": q, "per_page": per_page})
        body = resp.json()
    except GitHubError:
        return [], 0
    if not isinstance(body, dict):
        return [], 0
    items = body.get("items") or []
    if not isinstance(items, list):
        items = []
    nodes = [_rest_item_to_node(item) for item in items if isinstance(item, dict)]
    try:
        count = int(body.get("total_count") or len(nodes))
    except (TypeError, ValueError):
        count = len(nodes)
    return nodes, count


def _rest_item_to_node(item: dict[str, Any]) -> dict[str, Any]:
    license_info = (
        item.get("license") if isinstance(item.get("license"), dict) else None
    )
    spdx = license_info.get("spdx_id") if license_info else None
    lang = item.get("language")
    topics = item.get("topics") or []
    return {
        "id": item.get("node_id"),
        "databaseId": item.get("id"),
        "nameWithOwner": item.get("full_name"),
        "url": item.get("html_url"),
        "description": item.get("description"),
        "createdAt": item.get("created_at"),
        "pushedAt": item.get("pushed_at"),
        "isFork": bool(item.get("fork")),
        "isArchived": bool(item.get("archived")),
        "isDisabled": bool(item.get("disabled")),
        "isEmpty": False,
        "isMirror": False,
        "hasIssuesEnabled": item.get("has_issues"),
        "stargazerCount": item.get("stargazers_count") or 0,
        "forkCount": item.get("forks_count") or 0,
        "primaryLanguage": {"name": lang} if lang else None,
        "licenseInfo": {"spdxId": spdx} if spdx else None,
        "repositoryTopics": {"nodes": [{"topic": {"name": t}} for t in topics if t]},
    }


def _hit_from_graphql(node: dict[str, Any], key: str) -> SearchHit | None:
    nid = node.get("id")
    full = node.get("nameWithOwner")
    if not nid or not full:
        return None
    lang = node.get("primaryLanguage")
    language = lang.get("name") if isinstance(lang, dict) else None
    lic = node.get("licenseInfo")
    spdx = lic.get("spdxId") if isinstance(lic, dict) else None
    topics_raw = node.get("repositoryTopics") or {}
    topic_nodes = topics_raw.get("nodes") if isinstance(topics_raw, dict) else None
    topics: list[str] = []
    if isinstance(topic_nodes, list):
        for t in topic_nodes:
            if isinstance(t, dict) and isinstance(t.get("topic"), dict):
                name = t["topic"].get("name")
                if name:
                    topics.append(str(name))
    return SearchHit(
        node_id=str(nid),
        full_name=str(full),
        query_key=key,
        pool=pool_of(key),
        database_id=node.get("databaseId"),
        url=node.get("url"),
        description=node.get("description"),
        created_at=node.get("createdAt"),
        pushed_at=node.get("pushedAt"),
        is_fork=bool(node.get("isFork")),
        is_archived=bool(node.get("isArchived")),
        is_disabled=bool(node.get("isDisabled")),
        is_empty=bool(node.get("isEmpty")),
        is_mirror=bool(node.get("isMirror")),
        has_issues=node.get("hasIssuesEnabled"),
        stargazer_count=int(node.get("stargazerCount") or 0),
        fork_count=int(node.get("forkCount") or 0),
        language=language,
        license_spdx=spdx,
        topics=tuple(topics),
        raw=node,
    )


def cap_candidates(
    watchlist_ids: Sequence[Any],
    search_hits: Sequence[SearchHit],
    max_candidates: int = 120,
    disc: DiscoverySettings | None = None,
) -> CapResult:
    disc = disc or DiscoverySettings()
    watch: list[CappedCandidate] = []
    seen: set[str] = set()
    for item in watchlist_ids:
        if isinstance(item, str):
            nid, full, action = item, "", None
        else:
            nid = str(item.node_id)
            full = str(getattr(item, "full_name", "") or "")
            action = getattr(item, "action", None)
        if nid in seen:
            continue
        seen.add(nid)
        watch.append(
            CappedCandidate(
                node_id=nid, full_name=full, origin="watchlist", action=action
            )
        )
    truncated = len(watch) > max_candidates
    out = watch[:max_candidates]
    present = {c.node_id for c in out}
    kept = [h for h in search_hits if lightweight_keep(h)]
    hits_by_id = {h.node_id: h for h in kept}
    for cand in out:
        hit = hits_by_id.get(cand.node_id)
        if hit is not None:
            cand.query_key = hit.query_key
            cand.pool = hit.pool
            cand.hit = hit
            if not cand.full_name:
                cand.full_name = hit.full_name
    remaining = max(0, max_candidates - len(out))
    quotas = _scaled_quotas(
        {
            "A": disc.pool_a_quota,
            "B": disc.pool_b_quota,
            "C": disc.pool_c_quota,
        },
        remaining,
        max_candidates,
    )
    seated, overflow = _seat_pools(kept, present, quotas, disc.per_query_floor)
    for hit in seated:
        if len(out) >= max_candidates:
            overflow = True
            break
        out.append(
            CappedCandidate(
                node_id=hit.node_id,
                full_name=hit.full_name,
                origin="search",
                query_key=hit.query_key,
                pool=hit.pool,
                hit=hit,
            )
        )
        present.add(hit.node_id)
    return CapResult(
        candidates=out,
        watchlist_truncated=truncated,
        search_capped=overflow,
    )


def _scaled_quotas(
    quotas: dict[str, int], remaining: int, max_candidates: int
) -> dict[str, int]:
    """Scale 40:50:30 to remaining seats. Leftover from truncation goes A→B→C.

    This only sets exposure caps. Unused quota is never backfilled from another pool.
    """
    if remaining <= 0:
        return {key: 0 for key in quotas}
    if remaining >= max_candidates:
        return dict(quotas)
    out = {
        key: int(quotas[key] * remaining / max(max_candidates, 1)) for key in quotas
    }
    leftover = remaining - sum(out.values())
    for pool in POOL_ORDER:
        if leftover <= 0:
            break
        if quotas.get(pool, 0) <= 0:
            continue
        out[pool] = out.get(pool, 0) + 1
        leftover -= 1
    return out


def _seat_pools(
    kept: Sequence[SearchHit],
    present: set[str],
    quotas: dict[str, int],
    per_query_floor: int,
) -> tuple[list[SearchHit], bool]:
    """Round-robin within each pool up to quota. Never backfill unused quota."""
    by_pool: dict[str, list[SearchHit]] = {name: [] for name in POOL_ORDER}
    for hit in kept:
        if hit.node_id in present:
            continue
        by_pool.setdefault(hit.pool, []).append(hit)
    seated: list[SearchHit] = []
    overflow = False
    for pool in POOL_ORDER:
        quota = int(quotas.get(pool, 0))
        pool_hits = by_pool.get(pool) or []
        chosen = _round_robin_queries(pool_hits, quota, per_query_floor)
        seated.extend(chosen)
        if len(chosen) < len(pool_hits):
            overflow = True
    return seated, overflow


def _round_robin_queries(
    hits: Sequence[SearchHit], quota: int, per_query_floor: int
) -> list[SearchHit]:
    if quota <= 0 or not hits:
        return []
    groups: dict[str, list[SearchHit]] = {}
    order: list[str] = []
    for hit in hits:
        key = hit.query_key
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(hit)
    taken: set[str] = set()
    out: list[SearchHit] = []
    floor = max(0, per_query_floor)
    for key in order:
        for hit in groups[key][:floor]:
            if len(out) >= quota:
                return out
            if hit.node_id in taken:
                continue
            taken.add(hit.node_id)
            out.append(hit)
    progressed = True
    while progressed and len(out) < quota:
        progressed = False
        for key in order:
            for hit in groups[key]:
                if hit.node_id in taken:
                    continue
                taken.add(hit.node_id)
                out.append(hit)
                progressed = True
                break
            if len(out) >= quota:
                break
    return out


def identity_ids(
    capped: CapResult | Sequence[CappedCandidate], conn: sqlite3.Connection
) -> set[str]:
    cands = capped.candidates if isinstance(capped, CapResult) else list(capped)
    cand_ids = {c.node_id for c in cands}
    names: set[str] = set()
    for cand in cands:
        if cand.full_name:
            names.add(cand.full_name)
        else:
            row = conn.execute(
                "SELECT full_name FROM repos WHERE node_id=?", (cand.node_id,)
            ).fetchone()
            if row:
                names.add(row[0])
    known: set[str] = set()
    for nid in cand_ids:
        if conn.execute("SELECT 1 FROM repos WHERE node_id=?", (nid,)).fetchone():
            known.add(nid)
    collisions: set[str] = set()
    for name in names:
        for (nid,) in conn.execute(
            "SELECT node_id FROM repos WHERE full_name=? AND status='active'",
            (name,),
        ):
            collisions.add(nid)
    return known | collisions


def load_watchlist(
    conn: sqlite3.Connection, today: date, scoring: Any
) -> list[WatchlistEntry]:
    from foreshadow.reviews import _latest_join

    join_sql, join_params = _latest_join(conn, None)
    rows = conn.execute(
        f"""
        SELECT r.id, r.node_id, r.full_name, v.action, v.created_at
        FROM reviews v
        {join_sql}
        JOIN repos r ON r.id = v.repo_id
        ORDER BY v.created_at DESC, v.id DESC
        """,
        join_params,
    ).fetchall()
    out: list[WatchlistEntry] = []
    skip_days = int(getattr(scoring, "later_skip_days", 14))
    for repo_id, node_id, full_name, action, created_at in rows:
        created = _as_date(created_at)
        if action == "reject":
            continue
        if action == "later":
            if created is None or today < created + timedelta(days=skip_days):
                continue
        elif action not in {"watch", "interested", "investigate", "enter"}:
            continue
        out.append(
            WatchlistEntry(
                node_id=str(node_id),
                repo_id=int(repo_id),
                full_name=str(full_name),
                action=str(action),
                created_at=str(created_at),
            )
        )
    return out


def discovery_source(
    action: str | None, in_watchlist: bool, query_key: str | None
) -> str:
    if action == "enter":
        token = "active"
    elif in_watchlist:
        token = "watchlist"
    elif query_key:
        token = f"search:{query_key}"
    else:
        token = "search:unknown"
    if query_key and not token.startswith("search:"):
        token = f"{token}+search:{query_key}"
    return token


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def discover_hydrate_snapshot(
    conn: sqlite3.Connection,
    client: Any,
    settings: Settings,
    *,
    clock: Clock | None = None,
    force: bool = False,
) -> DiscoveryResult:
    clock = clock or Clock()
    today = clock.today()
    now = clock.now().isoformat()
    run_id = _begin_run(
        conn, today.isoformat(), settings.github.budget_graphql_points, now
    )
    health: dict[str, Any] = {
        "graphql": "ok",
        "search_truncated": False,
        "search_capped": False,
        "hydrate_failed": 0,
        "budget_abort": False,
        "watchlist_truncated": False,
    }
    hits = search_candidates(client, settings, today, force=force, health=health)
    watch = load_watchlist(conn, today, settings.scoring)
    watch_by_id = {w.node_id: w for w in watch}
    capped = cap_candidates(
        watch, hits, settings.discovery.max_candidates, disc=settings.discovery
    )
    health["watchlist_truncated"] = capped.watchlist_truncated
    health["search_capped"] = capped.search_capped
    ids = identity_ids(capped, conn)
    cand_id_set = {c.node_id for c in capped.candidates}
    collisions = ids - cand_id_set
    hydrated = apply_identity(conn, client, ids, hits, clock=clock, force=force)
    phase_a_ids = list(ids)
    for cand in capped.candidates:
        if cand.node_id in hydrated:
            continue
        body, err = hydrate_a_node(client, cand.node_id, force=force)
        phase_a_ids.append(cand.node_id)
        if err is not None:
            status = "not_found" if err.reason == "http_404" else "failed"
            repo_id = _ensure_candidate_repo(conn, cand, now)
            hydrated[cand.node_id] = HydratedRepo(
                node_id=cand.node_id,
                full_name=cand.full_name,
                repo_id=repo_id,
                status="not_found" if status == "not_found" else "incomplete",
                hydrate_status=status,
            )
            continue
        repo = extract_repo(body)
        if repo is None:
            repo_id = _ensure_candidate_repo(conn, cand, now)
            hydrated[cand.node_id] = HydratedRepo(
                node_id=cand.node_id,
                full_name=cand.full_name,
                repo_id=repo_id,
                status="not_found",
                hydrate_status="not_found",
            )
            continue
        repo_id = upsert_repo_from_graphql(conn, repo, now)
        hstatus = "incomplete" if graphql_marks_incomplete(body or {}) else "ok"
        hydrated[cand.node_id] = from_graphql(
            repo, repo_id=repo_id, hydrate_status=hstatus
        )

    bags = load_direction_bags()
    views: list[HydratedRepo] = []
    for cand in capped.candidates:
        view = hydrated.get(cand.node_id)
        if view is None:
            repo_id = _ensure_candidate_repo(conn, cand, now)
            view = HydratedRepo(
                node_id=cand.node_id,
                full_name=cand.full_name,
                repo_id=repo_id,
                hydrate_status="incomplete",
            )
            hydrated[cand.node_id] = view
        elif view.repo_id is None:
            view.repo_id = _ensure_candidate_repo(conn, cand, now)
        views.append(view)
        wl = watch_by_id.get(cand.node_id)
        action = (
            cand.action if cand.origin == "watchlist" else (wl.action if wl else None)
        )
        source = discovery_source(
            action,
            cand.origin == "watchlist" or wl is not None,
            cand.query_key,
        )
        conn.execute(
            """
            INSERT INTO candidates(run_id, repo_id, discovery_source, hydrate_status)
            VALUES (?,?,?,?)
            ON CONFLICT(run_id, repo_id) DO UPDATE SET
              discovery_source=excluded.discovery_source,
              hydrate_status=excluded.hydrate_status
            """,
            (run_id, view.repo_id, source, view.hydrate_status),
        )

    phase_b_views = phase_b_shortlist(
        views,
        watch,
        max_deep=settings.discovery.max_deep_hydrate,
        max_watchlist_deep=settings.discovery.max_watchlist_deep,
        cfg=settings.discovery,
        bags=bags,
        now=clock.now(),
        exclude_forks=settings.discovery.exclude_forks,
    )
    phase_b_ids = [v.node_id for v in phase_b_views]
    stop = getattr(client, "should_stop", lambda: False)
    if stop():
        health["budget_abort"] = True
    else:
        for view in phase_b_views:
            if stop():
                health["budget_abort"] = True
                break
            if view.hydrate_status == "not_found" or not view.owner:
                owner, name = _split_fn(view.full_name)
            else:
                owner, name = view.owner, view.name
            if not owner or not name:
                owner, name = _split_fn(view.full_name)
            body, err = hydrate_b_node(client, view.node_id, force=force)
            if err is not None:
                if err.reason == "http_404" or (err.status in {404, 410, 451}):
                    view.hydrate_status = "incomplete" if view.graphql else "not_found"
                elif view.hydrate_status != "not_found":
                    view.hydrate_status = "failed"
                continue
            repo = extract_repo(body)
            if repo is None:
                if view.graphql:
                    view.hydrate_status = "incomplete"
                continue
            if graphql_marks_incomplete(body or {}):
                view.hydrate_status = "incomplete"
            else:
                view.hydrate_status = "ok"
            view.graphql = repo
            if view.repo_id is not None:
                update_repo_from_graphql(conn, view.repo_id, repo, now)
            rest = hydrate_phase_b_rest(
                client, owner, name, clock, is_fork=view.is_fork
            )
            view.features = build_features_blob(repo, rest)
            c_rows = rest.get("contributors")
            if c_rows is None:
                view.contributor_count = None
                view.contributor_identified = None
                view.contributor_anon = None
                view.contributor_censored = None
            else:
                total, ident, anon, censored = census_contributors(c_rows)
                view.contributor_count = total
                view.contributor_identified = ident
                view.contributor_anon = anon
                view.contributor_censored = censored
            commits = rest.get("commits")
            view.unique_committers_30d = (
                None if commits is None else unique_committers_30d(commits)
            )
            live = from_graphql(
                repo, repo_id=view.repo_id, hydrate_status=view.hydrate_status
            )
            view.stargazerCount = live.stargazerCount
            view.full_name = live.full_name
            view.pushed_at = live.pushed_at
            view.topics = live.topics
            view.language = live.language
            view.description = live.description

    failed = 0
    for cand in capped.candidates:
        view = hydrated[cand.node_id]
        if view.hydrate_status == "failed":
            failed += 1
        conn.execute(
            "UPDATE candidates SET hydrate_status=? WHERE run_id=? AND repo_id=?",
            (view.hydrate_status, run_id, view.repo_id),
        )
        has_phase_a = (
            bool(view.graphql) and view.graphql.get("stargazerCount") is not None
        )
        if view.repo_id is None or not has_phase_a:
            continue
        feat = features_json(view.features)
        payload = payload_from_graphql(
            view.graphql,
            captured_at=now,
            created_at=view.created_at,
            features_json=feat,
            contributor_count=view.contributor_count,
            contributor_identified=view.contributor_identified,
            contributor_anon=view.contributor_anon,
            contributor_censored=view.contributor_censored,
            unique_committers_30d=view.unique_committers_30d,
        )
        upsert_snapshot(conn, view.repo_id, today, payload)
    health["hydrate_failed"] = failed
    health["budget_used"] = int(getattr(client, "graphql_used", 0) or 0)
    health["rest_used"] = int(getattr(client, "rest_used", 0) or 0)
    _persist_failures(conn, run_id, getattr(client, "source_failures", []), now)
    conn.execute(
        """
        UPDATE daily_runs SET
          status='running', finished_at=NULL, source_health_json=?,
          budget_used=?, budget_rest_used=?, candidate_count=?
        WHERE id=?
        """,
        (
            json.dumps(health, ensure_ascii=False),
            health["budget_used"],
            health["rest_used"],
            len(capped.candidates),
            run_id,
        ),
    )
    conn.commit()
    return DiscoveryResult(
        run_id=run_id,
        candidate_count=len(capped.candidates),
        phase_a_ids=phase_a_ids,
        phase_b_ids=phase_b_ids,
        identity_ids=ids,
        collisions=collisions,
        source_health=health,
        search_hits=hits,
        capped=capped,
    )


def _begin_run(
    conn: sqlite3.Connection, run_date: str, budget_cap: int, started_at: str
) -> int:
    conn.execute(
        """
        INSERT INTO daily_runs(run_date, started_at, status, budget_cap)
        VALUES (?, ?, 'running', ?)
        ON CONFLICT(run_date) DO UPDATE SET
          status='running',
          started_at=excluded.started_at,
          finished_at=NULL,
          error=NULL
        """,
        (run_date, started_at, budget_cap),
    )
    run_id = int(
        conn.execute(
            "SELECT id FROM daily_runs WHERE run_date=?", (run_date,)
        ).fetchone()[0]
    )
    conn.execute("DELETE FROM candidates WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM scores WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM score_compare WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM source_failures WHERE run_id=?", (run_id,))
    conn.commit()
    return run_id


def _ensure_candidate_repo(
    conn: sqlite3.Connection, cand: CappedCandidate, now: str
) -> int:
    row = conn.execute(
        "SELECT id FROM repos WHERE node_id=?", (cand.node_id,)
    ).fetchone()
    if row:
        return int(row[0])
    if cand.hit is not None:
        return insert_hit(conn, cand.hit, now)
    conn.execute(
        """
        INSERT INTO repos(node_id, full_name, owner, name, first_seen_at, last_seen_at)
        VALUES (?,?,?,?,?,?)
        """,
        (
            cand.node_id,
            cand.full_name or cand.node_id,
            (cand.full_name or "/").split("/", 1)[0],
            (cand.full_name or "/").split("/", 1)[-1],
            now,
            now,
        ),
    )
    return int(
        conn.execute(
            "SELECT id FROM repos WHERE node_id=?", (cand.node_id,)
        ).fetchone()[0]
    )


def _split_fn(full: str) -> tuple[str, str]:
    base = full.split("#", 1)[0]
    if "/" in base:
        owner, name = base.split("/", 1)
        return owner, name
    return "", base


def _persist_failures(
    conn: sqlite3.Connection, run_id: int, failures: Sequence[Any], now: str
) -> None:
    for fail in failures:
        conn.execute(
            """
            INSERT INTO source_failures(run_id, source, reason, detail, retryable, occurred_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                run_id,
                getattr(fail, "source", "") or "",
                getattr(fail, "reason", "") or "",
                getattr(fail, "detail", None),
                int(bool(getattr(fail, "retryable", True))),
                now,
            ),
        )
