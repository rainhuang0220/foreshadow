from foreshadow.board.html import render_board_html
from foreshadow.board.pipeline import assemble_board
from foreshadow.board.present import present_board
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
    assert "v7" in view["mode_reason_zh"]
    names = [c["full_name"] for c in view["candidates"]]
    scores = [c["final_score"] for c in view["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert names[0] == view["candidates"][0]["full_name"]
    top = view["candidates"][0]
    assert top["rank"] == 1
    assert top["rank_kind_zh"] == "预览排名"
    assert top["not_official"] is True
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
    assert "打开 GitHub" in html
    assert "数据完整度" in html
    assert "置信度" in html
    assert "活跃度" in html
    assert "不代表 Star 增长" in html
    assert "早期程度" in html
    assert "证据强度" in html
    assert "机会窗口" in html
    assert "activity_class_zh" in top
    assert '<html lang="zh-CN">' in html
    # list is summary-first: details live inside <details>, not as a wall of cards
    assert html.count("<details") >= 1
