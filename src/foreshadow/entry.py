"""Evidence-backed entry strategy (Plan A/B/C). Does not invent issue/PR ids."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.access import compute_access
from foreshadow.pipeline.strategy import HARD_LANGS, recommend_entry

STALE_DAYS = 3
ROUTES = ("ISSUE", "REPRO", "DOCS", "FIX", "ISSUE_FIRST")
_PRIORITY = {"ISSUE": 0, "REPRO": 1, "DOCS": 2, "ISSUE_FIRST": 3, "FIX": 4}
_FALLBACK_ROUTE = {
    "ISSUE": "ISSUE",
    "REPRODUCTION": "REPRO",
    "DOCUMENTATION": "DOCS",
    "TEST": "DOCS",
    "TOOLING": "DOCS",
    "BENCHMARK": "DOCS",
    "BUG_FIX": "FIX",
    "FEATURE": "FIX",
    "PERFORMANCE": "FIX",
    "INTEGRATION": "FIX",
    "DISCUSSION": "ISSUE_FIRST",
    "RESEARCH": "ISSUE_FIRST",
}
_HELP_LABELS = frozenset(
    {
        "help wanted",
        "help-wanted",
        "good first issue",
        "good-first-issue",
        "contribution welcome",
        "up for grabs",
    }
)
_GFI_LABELS = frozenset({"good first issue", "good-first-issue"})
_BUG_LABELS = frozenset({"bug", "crash", "defect", "regression"})
_DOCS_LABELS = frozenset({"documentation", "docs", "typo", "typing"})
_MAINT_ASSOC = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
_ISSUE_FIRST_RE = re.compile(
    r"(?is)("
    r"open an? issues? first|file an? issues? first|issue first|"
    r"discuss first|discussion first|please discuss|"
    r"talk to us first|rfc first|"
    r"don'?t (send|open) a pr|do not open a pr|"
    r"do not open a pull request|unsolicited prs?"
    r")"
)
_CLA_RE = re.compile(
    r"(?i)\bcla bot\b|contributor license(?: agreement)?|"
    r"\bsign the cla\b|\bcla assistant\b|\bcla\b"
)
_DCO_RE = re.compile(r"(?i)\bdco\b|signed-off-by|developer certificate of origin")
_PR_OK_RE = re.compile(
    r"(?i)prs? welcome|pull requests? (are )?welcome|patches welcome"
)
_HARD_TITLE_RE = re.compile(
    r"(?i)(rewrite|re-?architect|core engine|soundness|"
    r"undefined behaviour|cuda kernel|from scratch)"
)
_TODO_RE = re.compile(r"(?i)\b(TODO|FIXME|XXX)\b|error handling|unwrap\(")
_HASH_ISSUE_RE = re.compile(r"#(\d+)")
_TEXT_KEYS = (
    "contributing",
    "contributing_text",
    "contributing_md",
    "CONTRIBUTING.md",
    "readme_excerpt",
    "readme",
    "readme_text",
)


@dataclass
class EntryPlan:
    route: str
    title: str
    summary_zh: str
    issue_number: int | None
    pr_number: int | None
    why: list[str]
    effort: str
    risk: str
    confidence: float
    evidence: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "title": self.title,
            "summary_zh": self.summary_zh,
            "issue_number": self.issue_number,
            "pr_number": self.pr_number,
            "why": list(self.why),
            "effort": self.effort,
            "risk": self.risk,
            "confidence": self.confidence,
            "evidence": [dict(item) for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> EntryPlan:
        raw = data if isinstance(data, dict) else {}
        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), list) else []
        return cls(
            route=str(raw.get("route") or "ISSUE_FIRST"),
            title=str(raw.get("title") or ""),
            summary_zh=str(raw.get("summary_zh") or ""),
            issue_number=_as_int(raw.get("issue_number")),
            pr_number=_as_int(raw.get("pr_number")),
            why=[str(x) for x in (raw.get("why") or [])],
            effort=str(raw.get("effort") or "2h"),
            risk=str(raw.get("risk") or "low"),
            confidence=_clip01(float(raw.get("confidence") or 0.0)),
            evidence=[dict(x) for x in evidence if isinstance(x, dict)],
        )


@dataclass
class ContributionPolicy:
    wants_issue_first: bool
    unsolicited_pr_ok: bool
    cla: bool | None
    dco: bool | None
    good_first_issue_alive: bool | None
    notes_zh: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "wants_issue_first": self.wants_issue_first,
            "unsolicited_pr_ok": self.unsolicited_pr_ok,
            "cla": self.cla,
            "dco": self.dco,
            "good_first_issue_alive": self.good_first_issue_alive,
            "notes_zh": list(self.notes_zh),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ContributionPolicy:
        raw = data if isinstance(data, dict) else {}
        return cls(
            wants_issue_first=bool(raw.get("wants_issue_first")),
            unsolicited_pr_ok=bool(raw.get("unsolicited_pr_ok")),
            cla=_as_opt_bool(raw.get("cla")),
            dco=_as_opt_bool(raw.get("dco")),
            good_first_issue_alive=_as_opt_bool(raw.get("good_first_issue_alive")),
            notes_zh=[str(x) for x in (raw.get("notes_zh") or [])],
        )


@dataclass
class EntryStrategy:
    policy: ContributionPolicy
    recommended: EntryPlan
    alternatives: list[EntryPlan]
    analyzed_at: str
    stale_after: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy.as_dict(),
            "recommended": self.recommended.as_dict(),
            "alternatives": [p.as_dict() for p in self.alternatives],
            "analyzed_at": self.analyzed_at,
            "stale_after": self.stale_after,
        }


def analyze_entry(
    features: dict | FeaturesBlob,
    *,
    now: datetime,
    language: str | None = None,
) -> EntryStrategy:
    now = _aware(now)
    raw = _raw_map(features)
    blob = _blob(raw)
    lang = _language(raw, language)
    access = compute_access(blob)
    issues = _collect_issues(raw)
    prs = _collect_prs(raw)
    known_issues = {int(i["number"]) for i in issues if i.get("number") is not None}
    known_prs = {int(p["number"]) for p in prs if p.get("number") is not None}
    text = _culture_text(raw)
    policy = _policy(text, issues, now)
    hard = _hard_language(lang)
    low_access = _low_access(access, raw)
    has_todo = _has_todo(raw, issues)
    thin = _thin(raw, known_issues, text, has_todo)
    fallback = recommend_entry(blob, access=access, language=lang)
    fb_route = _map_fallback(fallback.path, has_issue_id=bool(known_issues))

    cands = _rank_candidates(
        issues=issues,
        known_issues=known_issues,
        raw=raw,
        policy=policy,
        hard=hard,
        low_access=low_access,
        has_todo=has_todo,
        thin=thin,
        lang=lang,
        fallback_route=fb_route,
        fallback_why=list(fallback.why),
    )
    ranked = sorted(
        cands.values(),
        key=lambda c: (-c["score"], _PRIORITY.get(c["route"], 9)),
    )
    plans: list[EntryPlan] = []
    seen: set[str] = set()
    for cand in ranked:
        route = cand["route"]
        if route in seen:
            continue
        issue_n = _checked_id(cand.get("issue_number"), known_issues)
        pr_n = _checked_id(cand.get("pr_number"), known_prs)
        if route in {"ISSUE", "REPRO"} and issue_n is None:
            continue
        plans.append(
            _to_plan(
                cand,
                issue_n=issue_n,
                pr_n=pr_n,
                thin=thin,
                hard=hard,
            )
        )
        seen.add(route)
        if len(plans) >= 3:
            break
    if not plans:
        plans.append(
            _to_plan(
                _issue_first_cand(
                    0.4, policy, thin, hard, low_access, list(fallback.why)
                ),
                issue_n=None,
                pr_n=None,
                thin=True,
                hard=hard,
            )
        )
    recommended = plans[0]
    if thin:
        recommended.confidence = min(recommended.confidence, 0.32)
        if recommended.route not in {"ISSUE_FIRST", "DOCS"}:
            docs = next((p for p in plans if p.route == "DOCS"), None)
            first = next((p for p in plans if p.route == "ISSUE_FIRST"), None)
            recommended = first or docs or recommended
            recommended.confidence = min(recommended.confidence, 0.32)
            plans = [recommended, *[p for p in plans if p.route != recommended.route]]
    alternatives = [p for p in plans[1:] if p.route != recommended.route][:2]
    return EntryStrategy(
        policy=policy,
        recommended=recommended,
        alternatives=alternatives,
        analyzed_at=now.isoformat(),
        stale_after=(now + timedelta(days=STALE_DAYS)).isoformat(),
    )


def persist_entry(
    conn: sqlite3.Connection, repo_id: int, strategy: EntryStrategy
) -> None:
    evidence = _merged_evidence(strategy)
    conn.execute(
        """
        INSERT INTO entry_analyses (
          repo_id, analyzed_at, stale_after, source_snapshot_date,
          policy_json, recommended_json, alternatives_json, evidence_json, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(repo_id) DO UPDATE SET
          analyzed_at=excluded.analyzed_at,
          stale_after=excluded.stale_after,
          source_snapshot_date=excluded.source_snapshot_date,
          policy_json=excluded.policy_json,
          recommended_json=excluded.recommended_json,
          alternatives_json=excluded.alternatives_json,
          evidence_json=excluded.evidence_json,
          confidence=excluded.confidence
        """,
        (
            int(repo_id),
            strategy.analyzed_at,
            strategy.stale_after,
            _source_snapshot_date(conn, repo_id),
            json.dumps(strategy.policy.as_dict(), ensure_ascii=False),
            json.dumps(strategy.recommended.as_dict(), ensure_ascii=False),
            json.dumps(
                [p.as_dict() for p in strategy.alternatives], ensure_ascii=False
            ),
            json.dumps(evidence, ensure_ascii=False),
            float(strategy.recommended.confidence),
        ),
    )
    conn.commit()


def load_entry(conn: sqlite3.Connection, repo_id: int) -> EntryStrategy | None:
    row = conn.execute(
        """
        SELECT analyzed_at, stale_after, policy_json, recommended_json, alternatives_json
        FROM entry_analyses WHERE repo_id=?
        """,
        (int(repo_id),),
    ).fetchone()
    if row is None:
        return None
    policy_raw = _load_json(row[2], {})
    rec_raw = _load_json(row[3], {})
    alts_raw = _load_json(row[4], [])
    alts = [EntryPlan.from_dict(x) for x in alts_raw if isinstance(x, dict)]
    return EntryStrategy(
        policy=ContributionPolicy.from_dict(
            policy_raw if isinstance(policy_raw, dict) else {}
        ),
        recommended=EntryPlan.from_dict(rec_raw if isinstance(rec_raw, dict) else {}),
        alternatives=alts,
        analyzed_at=str(row[0] or ""),
        stale_after=str(row[1] or ""),
    )


def _raw_map(features: dict | FeaturesBlob) -> dict[str, Any]:
    if isinstance(features, FeaturesBlob):
        return features.model_dump(mode="json", exclude_none=True)
    if isinstance(features, dict):
        return dict(features)
    return {}


def _blob(raw: dict[str, Any]) -> FeaturesBlob:
    try:
        return FeaturesBlob.model_validate(raw)
    except (TypeError, ValueError):
        return FeaturesBlob()


def _language(raw: dict[str, Any], language: str | None) -> str | None:
    if language and str(language).strip():
        return str(language).strip()
    if raw.get("language"):
        return str(raw["language"]).strip()
    primary = raw.get("primaryLanguage")
    if isinstance(primary, dict) and primary.get("name"):
        return str(primary["name"]).strip()
    return None


def _hard_language(language: str | None) -> bool:
    if not language:
        return False
    return language.strip().lower() in HARD_LANGS


def _low_access(access: Any, raw: dict[str, Any]) -> bool:
    klass = str(raw.get("access_class") or raw.get("access") or "").upper()
    if klass in {"LOW", "VERY_LOW"}:
        return True
    classification = getattr(access, "classification", None)
    if classification in {"LOW", "VERY_LOW"}:
        return True
    score = getattr(access, "score", None)
    return score is not None and float(score) < 35


def _culture_text(raw: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in _TEXT_KEYS:
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val)
    return "\n".join(parts)


def _policy(
    text: str, issues: list[dict[str, Any]], now: datetime
) -> ContributionPolicy:
    wants = bool(text and _ISSUE_FIRST_RE.search(text))
    pr_ok = (not wants) and bool(text and _PR_OK_RE.search(text))
    cla = True if text and _CLA_RE.search(text) else None
    dco = True if text and _DCO_RE.search(text) else None
    gfi = _gfi_alive(issues, now)
    notes: list[str] = []
    if not text.strip():
        notes.append("贡献文化未知（缺少 CONTRIBUTING / README 样本）")
    if wants:
        notes.append(
            "CONTRIBUTING/README 要求先开 Issue 或先讨论，不要直接提未征求的 PR"
        )
    if cla:
        notes.append("仓库要求 CLA（contributor license）")
    if dco:
        notes.append("仓库要求 DCO（Signed-off-by）")
    if gfi is True:
        notes.append("近 90 天内仍有开放的 good first issue")
    elif gfi is False:
        notes.append("样本里的 good first issue 已关闭或超过 90 天未更新")
    notes.extend(_maintainer_notes(issues))
    return ContributionPolicy(
        wants_issue_first=wants,
        unsolicited_pr_ok=pr_ok,
        cla=cla,
        dco=dco,
        good_first_issue_alive=gfi,
        notes_zh=notes,
    )


def _gfi_alive(issues: list[dict[str, Any]], now: datetime) -> bool | None:
    cutoff = now - timedelta(days=90)
    saw = False
    alive = False
    for iss in issues:
        labels = {str(x).lower() for x in (iss.get("labels") or [])}
        if not (labels & _GFI_LABELS):
            continue
        saw = True
        if not _is_open(iss):
            continue
        updated = iss.get("updated")
        if isinstance(updated, datetime) and updated >= cutoff:
            alive = True
    if not saw:
        return None
    return alive


def _maintainer_notes(issues: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for iss in issues:
        for cmt in iss.get("comments") or []:
            if not isinstance(cmt, dict):
                continue
            assoc = str(cmt.get("authorAssociation") or cmt.get("association") or "")
            if assoc not in _MAINT_ASSOC:
                continue
            number = iss.get("number")
            if number is not None:
                notes.append(f"维护者在 Issue #{int(number)} 上有回复")
            else:
                notes.append("维护者在开放 Issue 上有回复")
            break
        if len(notes) >= 3:
            break
    return notes


def _collect_issues(raw: dict[str, Any]) -> list[dict[str, Any]]:
    by_num: dict[int, dict[str, Any]] = {}
    extra: list[dict[str, Any]] = []

    def add(item: dict[str, Any]) -> None:
        number = item.get("number")
        if number is None:
            extra.append(item)
            return
        n = int(number)
        prev = by_num.get(n)
        if prev is None:
            by_num[n] = item
            return
        labels = sorted(set(prev.get("labels") or []) | set(item.get("labels") or []))
        merged = dict(prev)
        merged.update({k: v for k, v in item.items() if v not in (None, [], "")})
        merged["labels"] = labels
        if prev.get("url") and not item.get("url"):
            merged["url"] = prev["url"]
        by_num[n] = merged

    for key in ("issues", "issue_sample", "open_issues", "issues_open"):
        for node in _as_list(raw.get(key)):
            parsed = _parse_issue(node, default_open=True)
            if parsed:
                add(parsed)
    sample = raw.get("issuesOpenSample") or raw.get("issues_open_sample")
    if isinstance(sample, dict):
        for node in _as_list(sample.get("nodes")):
            parsed = _parse_issue(node, default_open=True)
            if parsed:
                add(parsed)
    elif isinstance(sample, list):
        for node in sample:
            parsed = _parse_issue(node, default_open=True)
            if parsed:
                add(parsed)
    for title in raw.get("help_issue_titles") or []:
        parsed = _issue_from_title(title, ["help wanted"])
        if parsed:
            add(parsed)
    for title in raw.get("open_issue_titles") or []:
        parsed = _issue_from_title(title, [])
        if parsed:
            add(parsed)
    for item in list(by_num.values()) + extra:
        number = item.get("number")
        if number is not None and not item.get("url"):
            item["url"] = _issue_url(raw, int(number), None)
    return list(by_num.values()) + extra


def _collect_prs(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    blobs: list[Any] = []
    for key in ("prs", "pulls", "pull_requests"):
        blobs.extend(_as_list(raw.get(key)))
    merged = raw.get("prsMerged") or raw.get("prs_merged")
    if isinstance(merged, dict):
        blobs.extend(_as_list(merged.get("nodes")))
    elif isinstance(merged, list):
        blobs.extend(merged)
    for node in blobs:
        if not isinstance(node, dict):
            continue
        number = _as_int(node.get("number"))
        if number is None or number in seen:
            continue
        seen.add(number)
        out.append(
            {
                "number": number,
                "title": str(node.get("title") or ""),
                "url": node.get("url") or node.get("html_url"),
            }
        )
    return out


def _parse_issue(node: Any, *, default_open: bool) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    number = _as_int(node.get("number"))
    title = str(node.get("title") or "")
    labels = _label_names(node.get("labels"))
    comments = []
    raw_comments = node.get("comments")
    if isinstance(raw_comments, dict):
        comments = [
            c for c in _as_list(raw_comments.get("nodes")) if isinstance(c, dict)
        ]
    elif isinstance(raw_comments, list):
        comments = [c for c in raw_comments if isinstance(c, dict)]
    state = node.get("state") or node.get("stateReason")
    if state is None and default_open:
        state = "OPEN"
    return {
        "number": number,
        "title": title,
        "state": str(state or "OPEN"),
        "labels": labels,
        "assignees_n": _assignees_n(node.get("assignees")),
        "updated": _parse_dt(
            node.get("updatedAt")
            or node.get("updated_at")
            or node.get("createdAt")
            or node.get("created_at")
        ),
        "url": node.get("url") or node.get("html_url"),
        "comments": comments,
    }


def _issue_from_title(text: Any, extra_labels: list[str]) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    match = _HASH_ISSUE_RE.search(raw)
    number = int(match.group(1)) if match else None
    title = raw
    if match:
        title = (raw[: match.start()] + raw[match.end() :]).strip(" :-—")
    return {
        "number": number,
        "title": title or raw,
        "state": "OPEN",
        "labels": list(extra_labels),
        "assignees_n": None,
        "updated": None,
        "url": None,
        "comments": [],
    }


def _label_names(raw: Any) -> list[str]:
    names: list[str] = []
    if raw is None:
        return names
    if isinstance(raw, str):
        return [p.strip() for p in raw.split(",") if p.strip()]
    nodes = raw.get("nodes") if isinstance(raw, dict) else raw
    for item in _as_list(nodes):
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]).strip())
    return names


def _assignees_n(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        if raw.get("totalCount") is not None:
            try:
                return int(raw["totalCount"])
            except (TypeError, ValueError):
                return None
        nodes = raw.get("nodes")
        if isinstance(nodes, list):
            return len(nodes)
        return None
    if isinstance(raw, list):
        return len(raw)
    return None


def _is_open(iss: dict[str, Any]) -> bool:
    state = str(iss.get("state") or "OPEN").upper()
    return state not in {"CLOSED", "MERGED"}


def _issue_url(raw: dict[str, Any], number: int, existing: str | None) -> str | None:
    if existing:
        return str(existing)
    base = raw.get("html_url")
    if isinstance(base, str) and "github.com" in base and number:
        return base.rstrip("/") + f"/issues/{number}"
    full = raw.get("full_name")
    if isinstance(full, str) and "/" in full and number:
        return f"https://github.com/{full}/issues/{number}"
    return None


def _has_todo(raw: dict[str, Any], issues: list[dict[str, Any]]) -> bool:
    hits = raw.get("todo_hits") or raw.get("todos") or []
    if isinstance(hits, list) and hits:
        return True
    if isinstance(hits, str) and hits.strip():
        return True
    for name in raw.get("tree_names") or []:
        if "todo" in str(name).lower():
            return True
    for iss in issues:
        if _TODO_RE.search(str(iss.get("title") or "")):
            return True
    return False


def _thin(
    raw: dict[str, Any], known_issues: set[int], text: str, has_todo: bool
) -> bool:
    if known_issues or has_todo or text.strip():
        return False
    if raw.get("issue_sample_n") not in (None, 0):
        return False
    return raw.get("pr_merged_sample_n") in (None, 0)


def _map_fallback(path: str, *, has_issue_id: bool) -> str:
    route = _FALLBACK_ROUTE.get(str(path), "ISSUE_FIRST")
    if route in {"ISSUE", "REPRO"} and not has_issue_id:
        return "ISSUE_FIRST"
    if route == "FIX" and not has_issue_id:
        return "ISSUE_FIRST"
    return route


def _rank_candidates(
    *,
    issues: list[dict[str, Any]],
    known_issues: set[int],
    raw: dict[str, Any],
    policy: ContributionPolicy,
    hard: bool,
    low_access: bool,
    has_todo: bool,
    thin: bool,
    lang: str | None,
    fallback_route: str,
    fallback_why: list[str],
) -> dict[str, dict[str, Any]]:
    small = _best_small_issue(issues)
    bug = _best_bug_issue(issues) or small
    docs_issue = _best_docs_issue(issues)
    cands: dict[str, dict[str, Any]] = {}

    cands["ISSUE_FIRST"] = _issue_first_cand(
        0.4, policy, thin, hard, low_access, fallback_why
    )
    docs_score = 0.42
    docs_why = ["从文档 / 示例 / typing 进入，代码风险较低"]
    if raw.get("gap_docs") == 1:
        docs_score += 0.18
        docs_why.append("仓库有文档缺口")
    if hard:
        docs_score += 0.16
        docs_why.append(f"主语言是 {lang}，不建议先改核心")
    if low_access:
        docs_score += 0.12
        docs_why.append("进入通道偏低，先文档而不是代码修复")
    docs_n = _as_int((docs_issue or {}).get("number")) if docs_issue else None
    docs_ev = (
        _issue_evidence(docs_issue) if docs_issue and docs_n in known_issues else []
    )
    if docs_n is not None:
        docs_why.append(f"样本里有文档向 Issue #{docs_n}")
    cands["DOCS"] = {
        "route": "DOCS",
        "score": docs_score,
        "issue_number": docs_n if docs_n in known_issues else None,
        "pr_number": None,
        "why": docs_why,
        "evidence": docs_ev,
        "title": "从文档 / 示例进入",
        "summary_zh": "先补文档、示例或 typing，避免一上来改核心实现",
        "help": False,
        "unassigned": False,
    }

    if small and small.get("number") in known_issues:
        n = int(small["number"])
        labels = {str(x).lower() for x in (small.get("labels") or [])}
        helpish = bool(labels & _HELP_LABELS)
        unassigned = small.get("assignees_n") in (None, 0)
        hard_title = bool(_HARD_TITLE_RE.search(str(small.get("title") or "")))
        if not hard_title:
            score = 0.8
            if helpish:
                score += 0.05
            if unassigned:
                score += 0.04
            if hard or low_access:
                score -= 0.04
            why = [f"开放样本有已确认的小 Issue #{n}：{small.get('title') or ''}"]
            if helpish:
                why.append("带 help wanted / good first issue 标签")
            if unassigned:
                why.append("当前未指派")
            cands["ISSUE"] = {
                "route": "ISSUE",
                "score": score,
                "issue_number": n,
                "pr_number": None,
                "why": why,
                "evidence": _issue_evidence(small),
                "title": f"跟进 Issue #{n}：{small.get('title') or ''}".strip("："),
                "summary_zh": f"从已确认的小 Issue #{n} 进入，不要直接提未对齐的 PR",
                "help": helpish,
                "unassigned": unassigned,
            }

    repro_src = bug if (bug and bug.get("number") in known_issues) else None
    if repro_src is None and small and small.get("number") in known_issues:
        repro_src = small
    if repro_src is not None:
        n = int(repro_src["number"])
        score = 0.55
        why = [f"先复现 Issue #{n}，再决定要不要动代码"]
        labels = {str(x).lower() for x in (repro_src.get("labels") or [])}
        if labels & _BUG_LABELS or _HARD_TITLE_RE.search(
            str(repro_src.get("title") or "")
        ):
            score += 0.12
            why.append("看起来像 bug / 回归，适合先写复现")
        if hard:
            score += 0.08
            why.append(f"主语言是 {lang}，复现比直接修更稳")
        cands["REPRO"] = {
            "route": "REPRO",
            "score": score,
            "issue_number": n,
            "pr_number": None,
            "why": why,
            "evidence": _issue_evidence(repro_src),
            "title": f"复现 Issue #{n}",
            "summary_zh": f"先按 Issue #{n} 在本机复现并记录现象",
            "help": False,
            "unassigned": False,
        }

    allow_fix = has_todo or (
        small is not None
        and not hard
        and not low_access
        and not policy.wants_issue_first
        and small.get("number") in known_issues
    )
    if allow_fix:
        score = 0.5
        why = ["证据里有 TODO / 错误处理或小 bug，可考虑最小修复"]
        if has_todo:
            score += 0.04
        if hard:
            score -= 0.28
            why.append(f"主语言是 {lang}，改核心风险高")
        if low_access:
            score -= 0.22
            why.append("进入通道偏低，未征求的修复容易被忽略")
        if policy.wants_issue_first:
            score -= 0.35
            why.append("贡献文化要求先 Issue")
        score = max(score, 0.15)
        fix_n = (
            int(small["number"])
            if small and small.get("number") in known_issues and not has_todo
            else None
        )
        cands["FIX"] = {
            "route": "FIX",
            "score": score,
            "issue_number": fix_n,
            "pr_number": None,
            "why": why,
            "evidence": _issue_evidence(small) if fix_n is not None else [],
            "title": "小范围代码修复" if not fix_n else f"小修复（Issue #{fix_n}）",
            "summary_zh": "仅在证据明确且文化允许时做最小代码修复",
            "help": False,
            "unassigned": False,
        }

    if fallback_route in cands:
        cands[fallback_route]["score"] += 0.06
        extra = [w for w in fallback_why if w and w not in cands[fallback_route]["why"]]
        cands[fallback_route]["why"].extend(extra[:2])
    elif fallback_route in ROUTES:
        cands[fallback_route] = {
            "route": fallback_route,
            "score": 0.45,
            "issue_number": None,
            "pr_number": None,
            "why": fallback_why or [f"沿用策略枚举 {fallback_route}"],
            "evidence": [],
            "title": _default_title(fallback_route, None),
            "summary_zh": _default_summary(fallback_route, None),
            "help": False,
            "unassigned": False,
        }
    return cands


def _issue_first_cand(
    base: float,
    policy: ContributionPolicy,
    thin: bool,
    hard: bool,
    low_access: bool,
    fallback_why: list[str],
) -> dict[str, Any]:
    score = base
    why = ["先起草 Issue / 讨论，不要默认提 PR"]
    if policy.wants_issue_first:
        score += 0.22
        why.append("贡献文化要求先开 Issue")
    if thin:
        score += 0.15
        why.append("证据不足，不能虚构 Issue 编号")
    if low_access:
        score += 0.1
    if hard:
        score += 0.08
    why.extend(w for w in fallback_why[:1] if w not in why)
    return {
        "route": "ISSUE_FIRST",
        "score": score,
        "issue_number": None,
        "pr_number": None,
        "why": why,
        "evidence": [],
        "title": "先起草 Issue，不要直接提 PR",
        "summary_zh": "先在本机写 ISSUE_DRAFT.md，等对齐后再考虑代码",
        "help": False,
        "unassigned": False,
    }


def _best_small_issue(issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked: list[tuple[int, dict[str, Any]]] = []
    for iss in issues:
        if iss.get("number") is None or not _is_open(iss):
            continue
        if _HARD_TITLE_RE.search(str(iss.get("title") or "")):
            continue
        labels = {str(x).lower() for x in (iss.get("labels") or [])}
        helpish = bool(labels & _HELP_LABELS)
        bug = bool(labels & _BUG_LABELS)
        docs = bool(labels & _DOCS_LABELS)
        if not (helpish or bug or docs):
            continue
        score = 0
        if helpish:
            score += 3
        if bug:
            score += 2
        if iss.get("assignees_n") in (None, 0):
            score += 1
        if docs:
            score += 1
        ranked.append((score, iss))
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked[0][1]


def _best_bug_issue(issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    for iss in issues:
        if iss.get("number") is None or not _is_open(iss):
            continue
        labels = {str(x).lower() for x in (iss.get("labels") or [])}
        title = str(iss.get("title") or "")
        if (
            labels & _BUG_LABELS
            or _HARD_TITLE_RE.search(title)
            or re.search(r"(?i)crash|bug|panic", title)
        ):
            return iss
    return None


def _best_docs_issue(issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    for iss in issues:
        if iss.get("number") is None or not _is_open(iss):
            continue
        labels = {str(x).lower() for x in (iss.get("labels") or [])}
        if labels & _DOCS_LABELS:
            return iss
    return None


def _issue_evidence(iss: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not iss or iss.get("number") is None:
        return []
    return [
        {
            "kind": "issue",
            "id": int(iss["number"]),
            "url": iss.get("url"),
        }
    ]


def _to_plan(
    cand: dict[str, Any],
    *,
    issue_n: int | None,
    pr_n: int | None,
    thin: bool,
    hard: bool,
) -> EntryPlan:
    route = str(cand["route"])
    effort, risk = _effort_risk(route, hard)
    conf = _plan_confidence(route, cand, thin=thin, has_id=issue_n is not None)
    evidence = []
    for item in cand.get("evidence") or []:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        evidence.append(
            {
                "kind": str(item.get("kind") or "issue"),
                "id": int(item["id"]),
                "url": item.get("url"),
            }
        )
    if issue_n is not None and not any(e.get("id") == issue_n for e in evidence):
        evidence.append({"kind": "issue", "id": issue_n, "url": None})
    return EntryPlan(
        route=route,
        title=str(cand.get("title") or _default_title(route, issue_n)),
        summary_zh=str(cand.get("summary_zh") or _default_summary(route, issue_n)),
        issue_number=issue_n,
        pr_number=pr_n,
        why=[str(x) for x in (cand.get("why") or []) if x],
        effort=effort,
        risk=risk,
        confidence=conf,
        evidence=evidence,
    )


def _effort_risk(route: str, hard: bool) -> tuple[str, str]:
    if route == "ISSUE":
        return "4h", "low"
    if route == "REPRO":
        return "6h", "low"
    if route == "DOCS":
        return "4h", "low"
    if route == "FIX":
        return "1d", "high" if hard else "medium"
    return "2h", "low"


def _plan_confidence(
    route: str, cand: dict[str, Any], *, thin: bool, has_id: bool
) -> float:
    if thin:
        return 0.22 if route == "ISSUE_FIRST" else 0.28
    if route == "ISSUE" and has_id:
        conf = 0.74
        if cand.get("help"):
            conf += 0.04
        if cand.get("unassigned"):
            conf += 0.04
        return _clip01(conf)
    if route == "REPRO" and has_id:
        return 0.62
    if route == "DOCS":
        return 0.55
    if route == "FIX":
        return 0.4
    return 0.48


def _default_title(route: str, issue_n: int | None) -> str:
    if route == "ISSUE" and issue_n is not None:
        return f"跟进 Issue #{issue_n}"
    if route == "REPRO" and issue_n is not None:
        return f"复现 Issue #{issue_n}"
    if route == "DOCS":
        return "从文档 / 示例进入"
    if route == "FIX":
        return "小范围代码修复"
    return "先起草 Issue，不要直接提 PR"


def _default_summary(route: str, issue_n: int | None) -> str:
    if route == "ISSUE" and issue_n is not None:
        return f"从已确认的小 Issue #{issue_n} 进入"
    if route == "REPRO" and issue_n is not None:
        return f"先复现 Issue #{issue_n}"
    if route == "DOCS":
        return "先补文档、示例或 typing"
    if route == "FIX":
        return "仅在证据明确时做最小代码修复"
    return "先起草 Issue，不要直接提 PR"


def _merged_evidence(strategy: EntryStrategy) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for plan in (strategy.recommended, *strategy.alternatives):
        for item in plan.evidence:
            kind = str(item.get("kind") or "issue")
            ident = item.get("id")
            if ident is None:
                continue
            key = (kind, int(ident))
            if key in seen:
                continue
            seen.add(key)
            out.append({"kind": kind, "id": int(ident), "url": item.get("url")})
    return out


def _source_snapshot_date(conn: sqlite3.Connection, repo_id: int) -> str | None:
    try:
        row = conn.execute(
            """
            SELECT snapshot_date FROM snapshots
            WHERE repo_id=? ORDER BY snapshot_date DESC LIMIT 1
            """,
            (int(repo_id),),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _load_json(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _as_list(raw: Any) -> list[Any]:
    return list(raw) if isinstance(raw, list) else []


def _as_int(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _as_opt_bool(raw: Any) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    return bool(raw)


def _checked_id(number: Any, known: set[int]) -> int | None:
    parsed = _as_int(number)
    if parsed is None or parsed not in known:
        return None
    return parsed


def _clip01(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 4)


def _aware(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
