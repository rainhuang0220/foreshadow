"""Chinese presentation layer. Does not change P0 or Chair numbers."""

from __future__ import annotations

import re
from typing import Any

from foreshadow.board.schema import BoardCard, BoardDocument, EvidenceItem
from foreshadow.reviews import ACTIONS

DIM_LABELS = {
    "momentum": "增长动能",
    "real_users": "真实用户",
    "contributor_gap": "贡献者缺口",
    "contribution_opportunity": "贡献机会",
    "early_entry": "提前进入",
}

REVIEWER_LABELS = {
    "trend": "趋势评审",
    "community": "社区评审",
    "contributor": "贡献评审",
}

ACTION_LABELS = {
    "watch": "关注",
    "interested": "感兴趣",
    "investigate": "调查",
    "enter": "记入观察清单（不是创建任务）",
    "later": "暂不考虑",
    "reject": "拒绝",
}

STATUS_LABELS = {
    "official": "正式入选",
    "preview_top": "预览候选",
    "deep": "深度评审",
    "shortlist": "高分候选",
    "excluded": "未入选",
    "vetoed": "硬规则否决",
}

DISAGREE_LABELS = {"HIGH": "高", "MEDIUM": "中", "LOW": "低"}
CONF_LABELS = {"low": "低", "medium": "中", "high": "高"}
COMPLETENESS_LABELS = {"low": "低", "medium": "中", "high": "高"}
ACTIVITY_CLASS_LABELS = {
    "VERY_LOW": "极低",
    "LOW": "低",
    "MEDIUM": "中",
    "HIGH": "高",
    "VERY_HIGH": "极高",
}
REC_LABELS = {
    "strong_candidate": "强候选",
    "candidate": "候选",
    "watch": "继续观察",
    "pass": "暂不推荐",
    "reject": "否决",
}

NA_NOTE = "当前历史数据不足，不参与虚假的补零。"

REVIEWER_FOCUS = {
    "trend": ["增长动能", "增长加速度", "外部关注", "技术趋势", "提前进入"],
    "community": ["真实用户", "贡献者缺口", "Issue", "PR", "维护者", "社区健康"],
    "contributor": [
        "真实未解决问题",
        "技术可行性",
        "贡献机会",
        "用户方向匹配",
        "成为长期贡献者的可能性",
    ],
}

_KV_RE = re.compile(r"([A-Za-z_]+)=([^\s,]+)")


def _n(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value)


def _access_view(card: BoardCard) -> tuple[str, float | None, bool]:
    """UNKNOWN omitted, never shown as 0. Known 0% merge stays 0."""
    score = card.access_score
    if score is None:
        return "未知", None, True
    label = ACTIVITY_CLASS_LABELS.get(card.access_class or "", "极低" if score == 0 else "未知")
    return label, score, False


def _short_time(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text


def _github_url(card: BoardCard) -> str:
    if card.html_url:
        return card.html_url
    return f"https://github.com/{card.full_name}"


def _status(card: BoardCard, board: BoardDocument) -> str:
    official = {c.full_name for c in board.official}
    provisional = {c.full_name for c in board.provisional}
    deep = {c.full_name for c in board.deep}
    if card.vetoed:
        return "vetoed"
    if card.full_name in official:
        return "official"
    if card.full_name in provisional:
        return "preview_top"
    if card.full_name in deep:
        return "deep"
    return "shortlist"


def _headline(card: BoardCard, status: str) -> str:
    if card.vetoed:
        return "硬规则否决，不进入候选。"
    dims = card.dimensions
    mom = dims.get("momentum")
    users = dims.get("real_users")
    gap = dims.get("contributor_gap")
    opp = dims.get("contribution_opportunity")
    early = dims.get("early_entry")
    if status in {"official", "preview_top"}:
        bits: list[str] = []
        if card.momentum_na or mom is None:
            bits.append("增长动能暂缺")
        elif mom >= 14:
            bits.append("增长动能较强")
        if (users or 0) >= 14:
            bits.append("真实用户有据")
        if (gap or 0) >= 14:
            bits.append("贡献者缺口明确")
        if (opp or 0) >= 14:
            bits.append("有可动手的问题")
        elif opp is not None and opp <= 10:
            bits.append("可切入贡献一般")
        if (early or 0) >= 14:
            bits.append("仍偏早期")
        prefix = "建议进入早期观察"
        if bits:
            return prefix + "：" + "，".join(bits[:3]) + "。"
        return prefix + "。"
    if card.momentum_na and (users or 0) >= 14:
        return "真实用户信号较强，但增长历史不足，尚未形成正式趋势。"
    if (gap or 0) <= 8 and (users or 0) >= 14:
        return "用户侧有信号，但贡献者缺口不够大。"
    if (opp or 0) <= 8:
        return "当前没有足够清晰的可切入贡献。"
    if (early or 0) <= 8:
        return "项目已经比较成熟，提前进入空间有限。"
    if mom is None:
        return "历史不足，综合分仅供预览，不是正式预测。"
    return "尚未进入今日前列，详情见淘汰原因。"


def _parse_kv(detail: str) -> dict[str, str]:
    return {k: v for k, v in _KV_RE.findall(detail or "")}


def _fmt_num(raw: str) -> str:
    try:
        n = float(raw)
    except ValueError:
        return raw
    if abs(n - round(n)) < 1e-6:
        return str(round(n))
    if abs(n) >= 10:
        return f"{n:.1f}"
    return f"{n:.2f}"


def _evidence_lines(item: EvidenceItem, snapshot_days: int) -> list[str]:
    detail = item.detail or ""
    kv = _parse_kv(detail)
    lines: list[str] = []
    if item.metric == "momentum":
        if item.observed is None or "insufficient" in detail.lower() or "N/A" in detail:
            lines.append(f"本地仅有 {snapshot_days} 天快照，v7 尚未形成。")
            lines.append(NA_NOTE)
            return lines
        if "rel_growth_7d" in kv:
            lines.append(f"近 7 日相对增长 {_fmt_num(kv['rel_growth_7d'])}")
        if "accel_ratio" in kv:
            lines.append(f"加速度比 {_fmt_num(kv['accel_ratio'])}")
    elif item.metric == "real_users":
        if "U_issue_ext" in kv:
            lines.append(f"外部用户相关 Issue 约 {_fmt_num(kv['U_issue_ext'])} 条")
        if "bug_n" in kv:
            lines.append(f"Bug 类 Issue {_fmt_num(kv['bug_n'])} 条")
        if "talk_n" in kv:
            lines.append(f"讨论类 Issue {_fmt_num(kv['talk_n'])} 条")
        if "fork_star" in kv:
            lines.append(f"Fork / Star ≈ {_fmt_num(kv['fork_star'])}")
        if kv.get("install") in {"1", "true", "True"}:
            lines.append("README 含安装说明")
    elif item.metric == "contributor_gap":
        if "C" in kv:
            lines.append(f"可识别贡献者 C = {_fmt_num(kv['C'])}")
        if "star_per_contrib" in kv:
            lines.append(f"每位贡献者对应 Stars ≈ {_fmt_num(kv['star_per_contrib'])}")
        if "demand_ratio" in kv:
            lines.append(f"需求比 {_fmt_num(kv['demand_ratio'])}")
        if kv.get("starved") in {"True", "true", "1"}:
            lines.append("维护带宽偏紧")
    elif item.metric == "contribution_opportunity":
        if "surface" in kv:
            lines.append(f"可贡献表面 {_fmt_num(kv['surface'])}")
        if "gaps" in kv:
            lines.append(f"工程缺口信号 {_fmt_num(kv['gaps'])}")
        if "receptive" in kv:
            lines.append(f"维护者可接近度 {_fmt_num(kv['receptive'])}")
        if "skill" in kv:
            lines.append(f"方向匹配 {_fmt_num(kv['skill'])}")
    elif item.metric == "early_entry":
        if "S" in kv:
            lines.append(f"当前 Stars {_fmt_num(kv['S'])}")
        if "C" in kv:
            lines.append(f"贡献者 {_fmt_num(kv['C'])}")
        if kv.get("late_now") in {"true", "True", "1"}:
            lines.append("按规模看已经偏成熟")
        elif kv.get("late_now") in {"false", "False", "0"}:
            lines.append("当前规模仍相对早期")
        if kv.get("late_10x") in {"true", "True", "1"}:
            lines.append("若再放大一个数量级，提前进入空间会明显变小")
    elif item.metric == "windows":
        if "v7=None" in detail or kv.get("v7") in {None, "None", ""}:
            lines.append(f"v7 不可用（快照天数 {snapshot_days}）。")
            lines.append(NA_NOTE)
        else:
            if kv.get("v7") and kv["v7"] != "None":
                lines.append(f"v7 = {_fmt_num(kv['v7'])}")
            if kv.get("v30") and kv["v30"] != "None":
                lines.append(f"v30 = {_fmt_num(kv['v30'])}")
    if not lines:
        if detail:
            lines.append(detail)
        elif item.observed:
            lines.append(f"观测值 {item.observed}")
    return lines


def _dimension_block(card: BoardCard, snapshot_days: int) -> list[dict[str, Any]]:
    by_metric: dict[str, list[EvidenceItem]] = {}
    for item in card.evidence:
        by_metric.setdefault(item.metric, []).append(item)
    out: list[dict[str, Any]] = []
    for key, label in DIM_LABELS.items():
        value = card.dimensions.get(key)
        na = value is None or (key == "momentum" and card.momentum_na)
        lines: list[str] = []
        for item in by_metric.get(key, []):
            lines.extend(_evidence_lines(item, snapshot_days))
        if key == "momentum" and na and not lines:
            lines = [f"本地仅有 {snapshot_days} 天快照，v7 尚未形成。", NA_NOTE]
        out.append(
            {
                "key": key,
                "label": label,
                "value": None if na else value,
                "max": 20,
                "na": na,
                "na_note": NA_NOTE if na and not lines else None,
                "evidence": lines,
            }
        )
    return out


def _reviewer_panel(card: BoardCard, which: str, snapshot_days: int) -> dict[str, Any]:
    r = getattr(card, which)
    dim_rows = []
    for key, label in DIM_LABELS.items():
        val = r.dimensions.get(key)
        na = val is None or (key == "momentum" and card.momentum_na)
        dim_rows.append(
            {
                "key": key,
                "label": label,
                "value": None if na else val,
                "max": 20,
                "na": na,
                "weight": r.weights.get(key),
            }
        )
    ev = []
    for item in r.evidence:
        ev.extend(_evidence_lines(item, snapshot_days))
    return {
        "id": which,
        "label": REVIEWER_LABELS[which],
        "focus": REVIEWER_FOCUS[which],
        "score": _n(r.score),
        "score_raw": r.score,
        "confidence": r.confidence,
        "confidence_zh": CONF_LABELS.get(r.confidence, r.confidence),
        "recommendation": r.recommendation,
        "recommendation_zh": REC_LABELS.get(r.recommendation, r.recommendation),
        "dimensions": dim_rows,
        "strengths": [_zh_strength(x) for x in r.strengths],
        "weaknesses": [_zh_weakness(x) for x in r.weaknesses],
        "risks": [_zh_risk(x) for x in r.risks],
        "evidence": ev[:8],
    }


def _zh_strength(text: str) -> str:
    for key, label in DIM_LABELS.items():
        if text.startswith(key + " "):
            return text.replace(key, label, 1)
    mapping = {
        "Momentum is N/A (insufficient snapshot history).": "增长动能暂为 N/A（历史不足）。",
        "no strong dimension yet.": "这一视角还没有特别突出的维度。",
    }
    for en, zh in mapping.items():
        if en in text:
            return zh
    return text


def _zh_weakness(text: str) -> str:
    return _zh_strength(text).replace(" is N/A.", " 暂为 N/A。")


def _zh_risk(text: str) -> str:
    if "insufficient" in text.lower() or text.startswith("NA"):
        return "历史仍然偏薄；在 v7 形成前只能当预览。"
    if text.startswith("v7=None"):
        return "v7 不可用，不能把当前分当成正式趋势。"
    return text


def disagreement_zh(card: BoardCard) -> dict[str, Any]:
    t, c, k = card.trend.score, card.community.score, card.contributor.score
    level = card.chair.disagreement
    tn, cn, kn = _n(t), _n(c), _n(k)
    if None in (tn, cn, kn):
        explain = "至少一位评审无法打出完整分数，分歧只能部分解释。"
    elif level == "HIGH" and (t or 0) >= 80 and (c or 0) <= 60:
        explain = (
            f"趋势评审认为增长信号较强（{tn}），"
            f"但社区评审认为真实用户证据不足（{cn}），因此出现较大分歧。"
        )
    elif level == "HIGH" and (k or 0) >= 80 and (t or 0) <= 60:
        explain = (
            f"贡献评审看到明确可切入的问题（{kn}），"
            f"但趋势评审认为增长动能不足（{tn}），因此出现较大分歧。"
        )
    elif level == "HIGH" and (c or 0) >= 70 and (t or 0) <= 55:
        explain = (
            f"社区评审认为真实用户痕迹更强（{cn}），"
            f"但趋势评审认为增长动能不足（{tn}），因此出现较大分歧。"
        )
    elif level == "HIGH":
        explain = (
            f"三个评审视角差得比较大：趋势 {tn}、社区 {cn}、贡献 {kn}。"
            "主审不会把分歧平均掉，而是单独记录。"
        )
    elif level == "MEDIUM":
        explain = (
            f"三个评审方向不完全一致：趋势 {tn}、社区 {cn}、贡献 {kn}，需要主审权衡。"
        )
    else:
        explain = "三个评审视角大体一致，综合评分主要反映共同判断。"
    return {
        "level": level,
        "level_zh": DISAGREE_LABELS.get(level, level),
        "trend": tn,
        "community": cn,
        "contributor": kn,
        "spread": card.chair.spread,
        "explain": explain,
    }


def _why_selected(card: BoardCard) -> list[str]:
    dims = card.dimensions
    bullets: list[str] = []
    mom = dims.get("momentum")
    if mom is not None and mom >= 14:
        bullets.append("最近窗口内增长动能较强")
    if (dims.get("contributor_gap") or 0) >= 14:
        bullets.append("贡献者数量明显落后于关注度，存在缺口")
    if (dims.get("contribution_opportunity") or 0) >= 14:
        bullets.append("Issue 中出现可明确动手的问题")
    if (dims.get("early_entry") or 0) >= 14:
        bullets.append("当前仍然处于相对早期")
    if (dims.get("real_users") or 0) >= 14:
        bullets.append("真实用户活动有据可查")
    if card.momentum_na:
        bullets.append("增长动能因历史不足记为 N/A，未用终身 Stars 冒充趋势")
    if not bullets:
        bullets.append("主审综合三个独立视角后，将其排在今日前列")
    return bullets[:6]


def _why_excluded(card: BoardCard) -> list[str]:
    bullets: list[str] = []
    if card.veto_reason:
        bullets.append(f"硬规则否决（{card.veto_reason}）")
    if card.momentum_na:
        bullets.append("增长趋势不足：v7 历史尚未形成，不能当作正式预测")
    dims = {k: v for k, v in card.dimensions.items() if v is not None}
    if dims:
        weakest = min(dims, key=lambda k: dims[k])
        val = dims[weakest]
        if val <= 12:
            mapping = {
                "momentum": "增长趋势不足",
                "real_users": "真实用户证据偏少",
                "contributor_gap": "贡献者缺口较小，可切入空间有限",
                "contribution_opportunity": "当前没有明显可切入贡献",
                "early_entry": "项目已经过于成熟，提前进入空间有限",
            }
            bullets.append(mapping[weakest])
    raw = card.chair.exclusion_reason or ""
    if "Out-ranked" in raw or "behind" in raw.lower():
        bullets.append("综合评分排在今日前五之后")
    if not bullets:
        bullets.append("主审审完证据后，认为整体案例弱于今日前列")
    # de-dup
    seen: set[str] = set()
    out: list[str] = []
    for b in bullets:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out[:6]


def _chair_judgment(card: BoardCard) -> str:
    dims = card.dimensions
    users = dims.get("real_users")
    gap = dims.get("contributor_gap")
    mom = dims.get("momentum")
    bits = []
    if mom is None:
        bits.append("项目增长信号无法用 v7 验证")
    elif mom >= 14:
        bits.append("项目增长信号较强")
    else:
        bits.append("项目增长信号一般")
    if (users or 0) >= 14:
        bits.append("社区已有真实用户痕迹")
    elif users is not None:
        bits.append("社区仍然偏小，真实用户规模尚未充分验证")
    if (gap or 0) >= 14:
        bits.append("存在明确贡献缺口")
    elif gap is not None:
        bits.append("贡献缺口不够突出")
    risk = "主要风险是长期用户规模尚未充分验证。"
    if card.chair.main_risk:
        weakest = None
        filled = {k: v for k, v in dims.items() if v is not None}
        if filled:
            weakest = min(filled, key=lambda k: filled[k])
        risk_map = {
            "momentum": "主要风险是增长还没有被本地快照验证。",
            "real_users": "主要风险是长期用户规模尚未充分验证。",
            "contributor_gap": "主要风险是贡献者缺口不够真实，后来者难站住。",
            "contribution_opportunity": "主要风险是眼下没有能做完的具体问题。",
            "early_entry": "主要风险是项目已经偏成熟，身份建设窗口在缩小。",
        }
        risk = risk_map.get(weakest or "", risk)
    return "，".join(bits) + "。" + risk


def present_card(
    card: BoardCard,
    board: BoardDocument,
    *,
    my_action: str | None = None,
    mission: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = _status(card, board)
    in_top5 = status in {"official", "preview_top"}
    rank_kind = "official" if board.mode == "official" else "preview"
    dims = _dimension_block(card, board.snapshot_days)
    acc_zh, acc_score, acc_unknown = _access_view(card)
    return {
        "rank": card.list_rank,
        "full_name": card.full_name,
        "owner": card.owner,
        "html_url": _github_url(card),
        "stars": card.stars,
        "forks": card.forks,
        "contributors": card.contributors,
        "open_issues": card.open_issues,
        "last_pushed_at": _short_time(card.last_pushed_at),
        "last_release": _short_time(card.last_release) or card.last_release,
        "first_seen_at": _short_time(card.first_seen_at),
        "description": card.description,
        "intro_zh": card.intro_zh,
        "intro_source": card.intro_source,
        "match_score": card.match_score,
        "match_reasons": list(card.match_reasons or []),
        "language": card.language,
        "final_score": _n(card.final_score),
        "final_score_raw": card.final_score,
        "trend": _n(card.trend.score),
        "community": _n(card.community.score),
        "contributor": _n(card.contributor.score),
        "chair": _n(card.chair.score),
        "headline": _headline(card, status),
        "status": status,
        "status_zh": STATUS_LABELS[status],
        "rank_kind": rank_kind,
        "rank_kind_zh": "正式排名" if rank_kind == "official" else "预览排名",
        "not_official": rank_kind != "official",
        "official_eligible": card.official_eligible,
        "momentum_na": card.momentum_na,
        "vetoed": card.vetoed,
        "data_completeness": card.data_completeness,
        "data_completeness_zh": COMPLETENESS_LABELS.get(
            card.data_completeness or "low", "低"
        ),
        "p0_confidence": card.p0_confidence,
        "p0_confidence_zh": CONF_LABELS.get(card.p0_confidence or "low", "低"),
        "activity_momentum": card.activity_momentum,
        "activity_class": card.activity_class,
        "activity_class_zh": ACTIVITY_CLASS_LABELS.get(card.activity_class or "", "未知"),
        "activity_confidence": card.activity_confidence,
        "activity_concentration": card.activity_concentration,
        "commits_7d": card.commits_7d,
        "commits_30d": card.commits_30d,
        "releases_30d": card.releases_30d,
        "recent_contributors_7d": card.recent_contributors_7d,
        "activity_note": "活跃度反映开发与社区活动，不代表 Star 增长。",
        "s1_stage": card.s1_stage,
        "s1_earlyness": card.s1_earlyness,
        "s1_evidence": card.s1_evidence,
        "s1_window": card.s1_window,
        "s1_pool": card.s1_pool,
        "s1_pool_zh": "实验池" if card.s1_pool == "experimental" else "主候选池",
        "s1_quadrant": card.s1_quadrant,
        "s1_earlyness_plus": list(card.s1_earlyness_plus or []),
        "s1_earlyness_minus": list(card.s1_earlyness_minus or []),
        "s1_evidence_plus": list(card.s1_evidence_plus or []),
        "s1_evidence_minus": list(card.s1_evidence_minus or []),
        "access_score": acc_score,
        "access_class": None if acc_unknown else card.access_class,
        "access_class_zh": acc_zh,
        "access_unknown": acc_unknown,
        "access_zero_note": "已知为 0，不是未知" if acc_score == 0 else None,
        "access_merge_rate": card.access_merge_rate,
        "access_review_rate": card.access_review_rate,
        "strategy_path": card.strategy_path,
        "strategy_summary_zh": card.strategy_summary_zh,
        "strategy_steps_zh": list(card.strategy_steps_zh or []),
        "strategy_difficulty": card.strategy_difficulty,
        "strategy_effort": card.strategy_effort,
        "strategy_long_term": card.strategy_long_term or {},
        "strategy_why": list(card.strategy_why or []),
        "why_now": card.why_now,
        "mission_id": (mission or {}).get("id"),
        "mission_status": (mission or {}).get("status"),
        "next_step_zh": (mission or {}).get("next_step_zh"),
        "needs_user_approval": bool((mission or {}).get("needs_user_approval")),
        "clone": (mission or {}).get("clone"),
        "pipeline": (mission or {}).get("pipeline"),
        "tests": (mission or {}).get("tests"),
        "my_action": my_action,
        "my_action_zh": ACTION_LABELS.get(my_action or "", None),
        "detail": {
            "dimensions": dims,
            "reviewers": [
                _reviewer_panel(card, "trend", board.snapshot_days),
                _reviewer_panel(card, "community", board.snapshot_days),
                _reviewer_panel(card, "contributor", board.snapshot_days),
            ],
            "disagreement": disagreement_zh(card),
            "chair": {
                "score": _n(card.chair.score),
                "blend_score": _n(card.chair.blend_score),
                "override": card.chair.override,
                "weights": {
                    "chair": 40,
                    "trend": 20,
                    "community": 20,
                    "contributor": 20,
                },
                "weight_note": "主审权重更高（40 / 20 / 20 / 20）",
                "judgment": _chair_judgment(card),
                "justification_zh": _chair_judgment(card),
                "main_risk": _risk_zh(card),
                "confidence_note": "置信度随 v7 与数据完整度变化；缺字段是 N/A，不是 0 分。",
                "data_completeness": card.data_completeness,
                "data_completeness_zh": COMPLETENESS_LABELS.get(
                    card.data_completeness or "low", "低"
                ),
                "p0_confidence": card.p0_confidence,
                "p0_confidence_zh": CONF_LABELS.get(card.p0_confidence or "low", "低"),
            },
            "why_selected": _why_selected(card) if in_top5 else None,
            "why_excluded": None if in_top5 else _why_excluded(card),
            "suggested_contribution": card.suggested_contribution,
            "p0": {
                "opportunity": _n(card.p0_opportunity),
                "explosion": _n(card.p0_explosion),
                "contribution": _n(card.p0_contribution),
                "explosion_na": card.p0_explosion is None,
            },
            "review_actions": [{"id": a, "label": ACTION_LABELS[a]} for a in ACTIONS],
        },
    }


def _risk_zh(card: BoardCard) -> str:
    filled = {k: v for k, v in card.dimensions.items() if v is not None}
    if card.momentum_na:
        return "增长还没有被本地快照验证，不能把预览分当成正式预测。"
    if not filled:
        return "证据仍然不完整。"
    weakest = min(filled, key=lambda k: filled[k])
    return {
        "momentum": "增长动能偏弱，近期加速不够明显。",
        "real_users": "真实用户规模尚未充分验证。",
        "contributor_gap": "贡献者缺口不够大，后来者难形成身份。",
        "contribution_opportunity": "眼下缺少能做完的具体问题。",
        "early_entry": "项目已经偏成熟，提前进入窗口在缩小。",
    }.get(weakest, "证据仍不完整。")


def present_board(
    board: BoardDocument,
    *,
    stances: dict[str, str] | None = None,
    missions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    stances = stances or {}
    missions = missions or {}
    ranked = sorted(
        board.shortlist,
        key=lambda c: (
            -(c.final_score or -1.0),
            -(c.trend.score or -1.0),
            -(c.contributor.score or -1.0),
            c.full_name,
        ),
    )
    candidates = [
        present_card(
            card,
            board,
            my_action=stances.get(card.full_name),
            mission=missions.get(card.full_name),
        )
        for card in ranked
    ]
    preview = board.mode != "official"
    return {
        "date": board.date,
        "mode": "preview" if preview else "official",
        "mode_zh": "预览模式" if preview else "正式模式",
        "mode_reason": board.mode_reason,
        "mode_reason_zh": (
            "历史数据不足 v7"
            if "v7" in board.mode_reason or "history" in board.mode_reason
            else ("正式模式，v7 历史完整" if not preview else "预览模式｜不是正式预测")
        ),
        "not_official_note": "这不是正式预测" if preview else None,
        "counts": {
            "discovered": board.discovered,
            "shortlisted": board.shortlisted,
            "deep_reviewed": board.deep_reviewed,
            "official_top5": board.official_top5,
            "provisional": board.provisional_count,
        },
        "snapshot_days": board.snapshot_days,
        "sort_default": "final_score",
        "sort_default_zh": "按综合评分从高到低",
        "candidates": candidates,
        "actions": [{"id": a, "label": ACTION_LABELS[a]} for a in ACTIONS],
    }
