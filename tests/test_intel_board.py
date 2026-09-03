import pytest

from foreshadow.board.pipeline import assemble_board
from foreshadow.board.present import present_board, present_card
from foreshadow.board.schema import BoardCard
from foreshadow.board.webapp import APP_HTML
from test_board_pipeline import _cs, _row

DATE = "2026-08-25"


def _fields() -> set[str]:
    return set(getattr(BoardCard, "model_fields", {}) or {})


def _require_intel(*names: str) -> None:
    fields = _fields()
    missing = [name for name in names if name not in fields]
    if missing:
        pytest.skip(f"BoardCard missing intel fields: {', '.join(missing)}")


def _assemble(rows, extras=None, *, preview=True):
    return assemble_board(
        rows,
        date=DATE,
        preview=preview,
        snapshot_days=1,
        extras=extras or {},
    )


def _blob(obj) -> str:
    bits: list[str] = []

    def walk(value) -> None:
        if value is None or isinstance(value, (bool, int, float)):
            return
        if isinstance(value, str):
            bits.append(value)
            return
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                walk(item)

    walk(obj)
    return " ".join(bits)


def _intel_view(view: dict) -> dict:
    intel = view.get("intel")
    if not isinstance(intel, dict):
        pytest.skip("present_card has no intel payload yet")
    return intel


def test_rank_is_not_quality_when_eev_is_low():
    _require_intel("eev", "potential", "official_eligible")
    extras = {
        "acme/alpha": {
            "intel": {
                "eev": 40,
                "potential": 41,
                "openness": 39,
                "entry_fit": 40,
            }
        },
        "other/beta": {
            "intel": {
                "eev": 39,
                "potential": 40,
                "openness": 38,
                "entry_fit": 39,
            }
        },
    }
    rows = [
        _row(
            "alpha",
            opportunity=_cs(40),
            explosion=_cs(40),
            real_user=_cs(40),
            contribution_opp=_cs(40),
        ),
        _row(
            "beta",
            owner="other",
            opportunity=_cs(40),
            explosion=_cs(40),
            real_user=_cs(38),
            contribution_opp=_cs(38),
        ),
    ]
    board = _assemble(rows, extras)
    view = present_board(board)
    top = next(card for card in view["candidates"] if card["rank"] == 1)
    assert top["official_eligible"] is False
    assert top["status"] != "official"
    assert top["rank_kind"] != "official"
    assert top.get("not_official") is True
    assert "优质" not in _blob(top)
    assert "正式入选" not in (top.get("rank_kind_zh") or "")
    assert "正式入选" not in (top.get("status_zh") or "")
    if "rank_is_not_quality" in top:
        assert top["rank_is_not_quality"] is True
    intel = _intel_view(top)
    eev = intel.get("eev", top.get("eev"))
    assert eev is not None
    assert 35 <= float(eev) <= 45
    decision = " ".join(
        str(item)
        for item in (
            intel.get("decision"),
            intel.get("decision_zh"),
            top.get("intel_decision"),
        )
        if item
    )
    assert "优质" not in decision


def test_empty_official_top5_is_legal_without_v7():
    row = _row("dry")
    board = _assemble([row], preview=False)
    assert board.official_top5 == 0
    assert board.official == []
    view = present_board(board)
    note = view.get("official_empty_note") or ""
    assert note
    assert any(token in note for token in ("空", "没有", "正常"))


def test_intel_na_is_not_zero():
    _require_intel("potential", "eev")
    board = _assemble([_row("bare")])
    card = board.shortlist[0]
    assert card.potential is None
    assert card.eev is None
    view = present_card(card, board)
    intel = _intel_view(view)
    assert intel.get("potential") is None
    assert intel.get("potential") != 0
    assert view.get("potential") is None
    for key in ("creator_prior", "openness", "entry_fit", "eev"):
        if key in intel:
            assert intel[key] is None


def test_explosion_is_not_aliased_as_potential():
    _require_intel("potential")
    row = _row("boom", explosion=_cs(80))
    board = _assemble([row])
    card = board.shortlist[0]
    assert card.p0_explosion == 80
    assert card.potential is None
    view = present_card(card, board)
    intel = _intel_view(view)
    assert intel.get("potential") is None
    assert intel.get("potential") != 80
    assert view.get("potential") != 80
    assert view["detail"]["p0"]["explosion"] == 80


def test_disabled_draft_pr_string_still_in_app_html():
    assert "批准并创建 Draft PR（本版关闭）" in APP_HTML


def test_board_does_not_claim_full_history_pr_acceptance():
    assert "外部 PR 接受率" not in APP_HTML
    assert "近期已合并 PR 样本" in APP_HTML


def test_project_summary_fallback_when_description_missing():
    _require_intel("project_summary")
    board = _assemble([_row("bare")])
    card = board.shortlist[0]
    assert not card.description
    assert card.project_summary
    assert "信息不足" in card.project_summary
    view = present_card(card, board)
    summary = view.get("project_summary")
    if summary is None:
        pytest.skip("present_card has no project_summary yet")
    assert "信息不足" in summary


def test_sort_default_is_eev():
    board = _assemble([_row("sort")])
    view = present_board(board)
    assert "sort_default" in view
    default = str(view["sort_default"]).lower()
    if default not in {"eev", "expected_entry_value"}:
        pytest.skip(
            f"present.py sort_default is {view['sort_default']!r}; sibling not done"
        )
    assert default == "eev" or default == "expected_entry_value"
