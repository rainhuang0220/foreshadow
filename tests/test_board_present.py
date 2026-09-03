from foreshadow.board.html import render_board_html
from foreshadow.board.pipeline import assemble_board
from foreshadow.board.present import present_board, present_card
from test_board_pipeline import _cs, _row


def test_present_board_is_chinese_and_sorted():
    rows = [
        _row("low", real_user=_cs(40), contribution_opp=_cs(40)),
        _row("high", owner="other", real_user=_cs(90), contribution_opp=_cs(90)),
    ]
    board = assemble_board(rows, date="2026-08-25", preview=True, snapshot_days=1)
    view = present_board(board)
    assert view["mode"] == "preview"
    assert view["mode_zh"] == "预览模式"
    assert "v7" not in view["mode_reason_zh"]
    assert "参考" in view["mode_reason_zh"]
    assert "v7" not in view["ribbon_zh"]
    assert "正式入选" in view["ribbon_zh"] or "参考" in view["ribbon_zh"]
    names = [c["full_name"] for c in view["candidates"]]
    scores = [c["final_score"] for c in view["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert names[0] == view["candidates"][0]["full_name"]
    top = view["candidates"][0]
    assert top["rank"] == 1
    assert top["rank_kind_zh"] == "参考排名"
    assert top["not_official"] is True
    assert top["confidence_zh"] == top["p0_confidence_zh"]
    assert "description" in top
    assert top["intro_zh"] is None
    assert top["intro_source"] == "limited"
    assert top["match_score"] is None
    assert top["match_reasons"] == []
    assert "language" in top
    assert "detail" in top
    d = top["detail"]
    labels = [x["label"] for x in d["dimensions"]]
    assert labels == ["增长动能", "真实用户", "贡献者缺口", "贡献机会", "提前进入"]
    mom = d["dimensions"][0]
    assert mom["na"] is True
    blob = " ".join([mom.get("na_note") or "", *(mom.get("evidence") or [])])
    assert "不参与虚假的补零" in blob
    rev_names = [r["label"] for r in d["reviewers"]]
    assert rev_names == ["趋势评审", "社区评审", "贡献评审"]
    assert d["disagreement"]["explain"]
    assert d["chair"]["weight_note"].startswith("主审权重更高")
    assert top["data_completeness_zh"] in {"高", "中", "低"}
    assert top["p0_confidence_zh"] in {"高", "中", "低"}
    html = render_board_html(board)
    assert "今日候选榜" in html
    assert "为什么现在：" in html
    assert "空 Top 5 是成功" not in html
    assert "v7" not in html
    for leak in (
        "node_id",
        "TTL",
        "admission",
        "migration",
        "worktree",
        "dogfood",
        "FakeGitHub",
        "P0",
        "P1",
    ):
        assert leak not in html
    view = present_board(board)
    actions = view["candidates"][0]["detail"]["review_actions"]
    enter = next(a for a in actions if a["id"] == "enter")
    assert "开始进入" not in enter["label"]
    assert "观察" in enter["label"]
    missions = {
        top["full_name"]: {
            "id": 9,
            "status": "WAITING_USER_APPROVAL",
            "next_step_zh": "准备本地环境",
            "needs_user_approval": True,
            "clone": {"ok": True, "status": "cloned"},
            "pipeline": [{"id": "clone", "status": "done", "label_zh": "克隆仓库"}],
        }
    }
    joined = present_board(board, missions=missions)
    hit = joined["candidates"][0]
    assert hit["mission_id"] == 9
    assert hit["mission_status"] == "WAITING_USER_APPROVAL"
    assert hit["clone"]["ok"] is True
    assert hit["pipeline"][0]["id"] == "clone"
    assert "why_now" in hit
    assert hit["needs_user_approval"] is True
    assert hit.get("access_unknown") is True
    assert hit.get("access_score") is None
    assert hit.get("access_class_zh") == "未知"
    assert "打开 GitHub" in html
    assert "数据完整度" in html
    assert "置信度" in html
    assert "活跃度" in html
    assert "不代表 Star 增长" in html
    assert "早期程度" in html
    assert "证据强度" in html
    assert "机会窗口" in html
    assert "进入通道" in html
    assert "activity_class_zh" in top
    assert '<html lang="zh-CN">' in html
    # list is summary-first: details live inside <details>, not as a wall of cards
    assert html.count("<details") >= 1


def test_present_card_includes_intro_and_match_overlay():
    row = _row("mem")
    extras = {
        "acme/mem": {
            "description": "Local-first long-term memory for RAG pipelines",
            "language": "Python",
            "topics": ["rag", "memory", "llm"],
        }
    }
    board = assemble_board(
        [row],
        date="2026-08-25",
        preview=True,
        snapshot_days=1,
        extras=extras,
    )
    card = board.shortlist[0]
    view = present_card(card, board)
    assert view["description"] == extras["acme/mem"]["description"]
    assert view["intro_zh"] == extras["acme/mem"]["description"]
    assert view["intro_source"] == "github"
    assert view["language"] == "Python"
    assert view["match_score"] is not None
    assert 0 <= view["match_score"] <= 100
    assert "RAG/memory" in view["match_reasons"]
    assert view["final_score"] == (
        round(card.final_score) if card.final_score is not None else None
    )


def test_observation_badge_is_product_copy():
    extras = {"acme/mem": {"observation_age_days": 4}}
    board = assemble_board(
        [_row("mem")],
        date="2026-08-25",
        preview=True,
        snapshot_days=1,
        extras=extras,
    )
    view = present_card(board.shortlist[0], board)
    assert view["observation_zh"] == "持续观察 · 第 4 天"
    assert view["observation_kind"] == "watching"
    assert view["observation_hint"]
    watched = present_card(board.shortlist[0], board, my_action="watch")
    assert watched["observation_zh"] == "你的关注"
    assert watched["observation_kind"] == "yours"
    html = render_board_html(board)
    assert "持续观察 · 第 4 天" in html
    assert "node_id" not in html
    assert "TTL" not in html


def test_empty_official_is_success_copy():
    board = assemble_board([], date="2026-08-25", preview=True, snapshot_days=1)
    view = present_board(
        board,
        run={"any_run": True, "status": "complete", "health": {}},
    )
    assert view["empty"]["kind"] == "empty_success"
    assert view["empty"]["is_success"] is True
    assert "故障" in view["empty"]["body"]
    html = render_board_html(board)
    assert "foreshadow run" in html or "今日没有可展示的项目" in html
    assert "空 Top 5 是成功" not in html


def test_never_run_and_degraded_are_not_success():
    board = assemble_board([], date="2026-08-25", preview=True, snapshot_days=1)
    never = present_board(board, run={"any_run": False, "status": None, "health": {}})
    assert never["empty"]["kind"] == "never_run"
    assert never["empty"]["is_success"] is False
    assert never["empty"]["action"] == "foreshadow run"
    assert "还没有扫描记录" in never["empty"]["title"]
    degraded = present_board(
        board,
        run={
            "any_run": True,
            "status": "degraded",
            "health": {"search_truncated": True, "hydrate_failed": 2},
        },
    )
    assert degraded["empty"]["is_success"] is False
    assert degraded["empty"]["kind"] == "degraded"
    assert degraded["run"]["status_zh"] == "扫描不完整"
    assert any("截断" in x for x in degraded["run"]["reasons_zh"])
    assert degraded["official_empty_note"] is None


def test_present_intel_na_empty_official_and_rank_is_not_quality():
    row = _row("mem", explosion=_cs(80))
    board = assemble_board(
        [row],
        date="2026-08-25",
        preview=True,
        snapshot_days=1,
        extras={"acme/mem": {"description": None}},
    )
    assert board.official_top5 == 0
    assert board.shortlist[0].eev is None
    assert board.shortlist[0].potential is None
    assert board.shortlist[0].project_summary == "信息不足，无法写简介。"
    view = present_board(
        board,
        run={"any_run": True, "status": "complete", "health": {}},
    )
    assert view["official_empty_note"]
    assert "正式入选" in view["official_empty_note"]
    assert view["sort_default"] == "eev"
    assert view["sort_default_zh"] == "按预期进入价值"
    assert view["no_high_confidence_note"] == "今天没有高置信机会。以下为参考排名。"
    scores = [c["final_score"] for c in view["candidates"]]
    assert scores == sorted(scores, reverse=True)
    card = view["candidates"][0]
    intel = card["intel"]
    assert intel["eev"] is None
    assert intel["potential"] is None
    assert intel["creator_prior"] is None
    assert intel["openness"] is None
    assert intel["entry_fit"] is None
    assert intel["eev_zh"] == "N/A"
    assert intel["potential_zh"] == "N/A"
    assert intel["na_note"] == "数据不足，不是 0"
    assert intel["creator_prior_na_note"] == "尚未建模，不是 0"
    assert intel["eev"] != 0
    assert 0 not in (
        intel["eev"],
        intel["potential"],
        intel["creator_prior"],
        intel["openness"],
        intel["entry_fit"],
    )
    assert "explosion" not in intel
    assert card["detail"]["p0"]["explosion"] == 80
    assert card["project_summary"] == "信息不足，无法写简介。"
    assert card["rank_is_not_quality"] is True
    assert "参考排名" in card["rank_footnote_zh"]
    assert "质量" in card["rank_footnote_zh"]
    assert card["eev"] is None
    assert card["creator"] is None
    mixed = assemble_board(
        [
            _row("low", real_user=_cs(90), contribution_opp=_cs(90)),
            _row("high", owner="other", real_user=_cs(40), contribution_opp=_cs(40)),
        ],
        date="2026-08-25",
        preview=True,
        snapshot_days=1,
        extras={
            "acme/low": {"intel": {"eev": 10}},
            "other/high": {"intel": {"eev": 80}},
        },
    )
    ordered = present_board(mixed)["candidates"]
    assert [c["full_name"] for c in ordered] == ["other/high", "acme/low"]
    assert ordered[0]["intel"]["eev"] == 80
    assert ordered[1]["intel"]["eev"] == 10
    assert mixed.shortlist[0].list_rank != mixed.shortlist[1].list_rank
    by_name = {c.full_name: c.list_rank for c in mixed.shortlist}
    assert by_name["other/high"] == 1
    assert by_name["acme/low"] == 2
