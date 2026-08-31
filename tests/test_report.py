import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fakes import FakeGitHub, repo_node, seed_repo, seed_review
from foreshadow.cli import app
from foreshadow.config import Settings
from foreshadow.db import connect, migrate
from foreshadow.models import ReportJSON
from foreshadow.pipeline import run_pipeline
from foreshadow.pipeline.report import (
    build_card,
    build_report,
    render_json,
    render_markdown,
)
from foreshadow.pipeline.score import score_repo
from foreshadow.pipeline.select import select_top

ROOT = Path(__file__).resolve().parents[1]
EMPTY_GOLDEN = ROOT / "examples" / "report-sample-empty.md"
SAMPLE_GOLDEN = ROOT / "examples" / "report-sample.md"

CARD_KEYS = (
    "rank",
    "node_id",
    "full_name",
    "html_url",
    "opportunity",
    "explosion",
    "contribution",
    "confidence",
    "momentum",
    "real_user",
    "gap",
    "contribution_opp",
    "early_entry",
    "direction_fit",
    "maintainer",
    "flags",
    "exceptional",
    "vetoed",
    "veto_reason",
    "why_now",
    "windows",
    "components",
    "evidence_ref",
)

REPORT_KEYS = (
    "date",
    "status",
    "reason",
    "top5_count",
    "candidate_count",
    "scored_count",
    "budget_used",
    "budget_cap",
    "budget_rest_used",
    "snapshot_days",
    "cards",
    "active",
    "watchlist_appendix",
    "below_bar",
    "rejected_counts",
    "source_health",
)

ZERO_REJECTED = {
    "H1": 0,
    "H2": 0,
    "H3": 0,
    "H4": 0,
    "H5": 0,
    "H6": 0,
    "H7": 0,
    "H8": 0,
    "H9": 0,
    "H10": 0,
    "fake_spike": 0,
    "below_threshold": 0,
    "momentum_low": 0,
    "direction": 0,
    "review_filter": 0,
    "incomplete_tree": 0,
}

SOURCE_OK = {
    "graphql": "ok",
    "search_truncated": False,
    "search_capped": False,
    "hydrate_failed": 0,
    "budget_abort": False,
    "watchlist_truncated": False,
}

FORBIDDEN = ("will explode", "next langchain", "guaranteed")


def empty_report(**over) -> ReportJSON:
    payload = {
        "date": "2026-08-24",
        "status": "complete",
        "reason": "no_eligible_opportunities",
        "top5_count": 0,
        "candidate_count": 0,
        "scored_count": 0,
        "budget_used": 0,
        "budget_cap": 800,
        "budget_rest_used": 0,
        "snapshot_days": 1,
        "cards": [],
        "active": [],
        "watchlist_appendix": [],
        "below_bar": [],
        "rejected_counts": dict(ZERO_REJECTED),
        "source_health": dict(SOURCE_OK),
    }
    payload.update(over)
    return ReportJSON(**payload)


def _with_ids(repo: dict, node_id: str) -> dict:
    out = dict(repo)
    out["node_id"] = node_id
    out["html_url"] = f"https://github.com/{repo['full_name']}"
    return out


def twelve_a_report(frozen_clock, repo_fixture) -> ReportJSON:
    memkit = _with_ids(repo_fixture("memkit.json"), "R_kgDOEXAMPLE")
    giant = _with_ids(repo_fixture("giant.json"), "R_giant")
    wrapper = _with_ids(repo_fixture("wrapper.json"), "R_wrap")
    a = score_repo(memkit, clock=frozen_clock)
    b = score_repo(giant, clock=frozen_clock)
    c = score_repo(wrapper, clock=frozen_clock)
    selected = select_top([a, b, c])
    return build_report(
        date="2026-08-24",
        status="complete",
        scored_rows=[(a, memkit), (b, giant), (c, wrapper)],
        selected=selected,
        candidate_count=3,
        scored_count=3,
        budget_used=0,
        budget_cap=800,
        budget_rest_used=0,
        snapshot_days=31,
        source_health=dict(SOURCE_OK),
        captured_at="2026-08-24T00:05:00+00:00",
    )


def isolate(tmp_home, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_home))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.delenv("FORESHADOW_CONFIG", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_home


def mini_github(full_name: str = "acme/toy", node_id: str = "R_toy", **over):
    node = repo_node(node_id, full_name, **over)
    return FakeGitHub(nodes={node_id: node}, search_nodes=[node]), node


def test_empty_report_matches_golden():
    md = render_markdown(empty_report())
    assert md == EMPTY_GOLDEN.read_text(encoding="utf-8")
    dumped = json.loads(render_json(empty_report()))
    assert list(dumped) == list(REPORT_KEYS)
    assert dumped["reason"] == "no_eligible_opportunities"
    assert dumped["cards"] == []
    assert dumped["top5_count"] == 0


def test_header_contains_v7():
    md = render_markdown(empty_report())
    assert "v7" in md
    md31 = render_markdown(
        empty_report(snapshot_days=31, reason="no_eligible_opportunities")
    )
    assert "v7" in md31


def test_12a_card_json_keys(frozen_clock, repo_fixture):
    report = twelve_a_report(frozen_clock, repo_fixture)
    assert report.top5_count == 1
    assert len(report.cards) == 1
    card = report.cards[0]
    assert set(CARD_KEYS) <= set(card)
    assert card["full_name"] == "acme/memkit"
    assert card["rank"] == 1
    assert card["node_id"] == "R_kgDOEXAMPLE"
    dumped = json.loads(render_json(report))
    assert list(dumped) == list(REPORT_KEYS)
    assert set(CARD_KEYS) <= set(dumped["cards"][0])
    built = build_card(
        score_repo(repo_fixture("memkit.json"), clock=frozen_clock),
        rank=1,
        repo=_with_ids(repo_fixture("memkit.json"), "R_kgDOEXAMPLE"),
        captured_at="2026-08-24T00:05:00+00:00",
    )
    assert set(CARD_KEYS) <= set(built)


def test_sample_report_matches_golden(frozen_clock, repo_fixture):
    md = render_markdown(twelve_a_report(frozen_clock, repo_fixture))
    assert md == SAMPLE_GOLDEN.read_text(encoding="utf-8")
    assert "700 net stars in 7 days on a 200-star base" in md
    assert "22 unique external issue authors" in md
    assert "v7" in md


def test_renderer_emits_at_most_five_cards(frozen_clock, repo_fixture):
    memkit = _with_ids(repo_fixture("memkit.json"), "R_m")
    scored = score_repo(memkit, clock=frozen_clock)
    cards = []
    for i in range(1, 8):
        card = build_card(scored, rank=i, repo={**memkit, "full_name": f"acme/r{i}"})
        card["full_name"] = f"acme/r{i}"
        card["rank"] = i
        cards.append(card)
    md = render_markdown(
        empty_report(
            top5_count=7,
            cards=cards,
            snapshot_days=31,
            reason=None,
            candidate_count=7,
            scored_count=7,
        )
    )
    assert md.count("### #") == 5
    low = md.lower()
    for phrase in FORBIDDEN:
        assert phrase not in low


def test_no_prophecy_phrases(frozen_clock, repo_fixture):
    md = render_markdown(twelve_a_report(frozen_clock, repo_fixture))
    low = md.lower()
    for phrase in FORBIDDEN:
        assert phrase not in low
    js = render_json(twelve_a_report(frozen_clock, repo_fixture)).lower()
    for phrase in FORBIDDEN:
        assert phrase not in js


def test_run_pipeline_empty_top5_complete(
    tmp_home, tmp_path, frozen_clock, monkeypatch
):
    isolate(tmp_home, tmp_path, monkeypatch)
    gh, _ = mini_github()
    result = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert result.status == "complete"
    assert result.top5_count == 0
    assert result.report_path is not None
    md = Path(result.report_path).read_text(encoding="utf-8")
    assert "v7" in md
    assert "**Top 5: 0**" in md
    js = json.loads(
        Path(result.report_path).with_suffix(".json").read_text(encoding="utf-8")
    )
    assert js["status"] == "complete"
    assert js["top5_count"] == 0
    assert js["reason"] == "no_eligible_opportunities"
    conn = connect(tmp_home / "foreshadow.sqlite3")
    row = conn.execute(
        "SELECT status, top5_count, scored_count, report_path FROM daily_runs"
    ).fetchone()
    assert row[0] == "complete"
    assert row[1] == 0
    assert row[3].endswith("2026-08-24.md")


def test_search_truncated_is_degraded_search_capped_is_not(
    tmp_home, tmp_path, frozen_clock, monkeypatch
):
    isolate(tmp_home, tmp_path, monkeypatch)
    gh, _ = mini_github()
    gh.search_total_override = 400
    result = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert result.status == "degraded"
    md = Path(result.report_path).read_text(encoding="utf-8")
    assert "**degraded**" in md

    isolate(tmp_home, tmp_path, monkeypatch)
    nodes = [repo_node(f"R_{i}", f"acme/r{i}") for i in range(3)]
    capped = FakeGitHub(
        nodes={n["id"]: n for n in nodes},
        search_nodes=nodes,
    )
    settings = Settings()
    settings.discovery.max_candidates = 1
    result = run_pipeline(
        clock=frozen_clock, force=True, llm=False, client=capped, settings=settings
    )
    assert result.source_health.get("search_capped") is True
    assert result.status == "complete"


def test_force_only_when_complete(tmp_home, tmp_path, frozen_clock, monkeypatch):
    isolate(tmp_home, tmp_path, monkeypatch)
    gh, _ = mini_github()
    first = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    n1 = gh.hydrate_calls
    skipped = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert skipped.status == "complete"
    assert skipped.skipped is True
    assert skipped.report_path == first.report_path
    assert gh.hydrate_calls == n1
    forced = run_pipeline(clock=frozen_clock, force=True, llm=False, client=gh)
    assert forced.skipped is False
    assert gh.hydrate_calls > n1

    conn = connect(tmp_home / "foreshadow.sqlite3")
    conn.execute("UPDATE daily_runs SET status='degraded' WHERE run_date='2026-08-24'")
    conn.commit()
    again = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert again.skipped is True
    assert again.status == "degraded"
    assert again.skip_reason == "same_day"
    forced_deg = run_pipeline(clock=frozen_clock, force=True, llm=False, client=gh)
    assert forced_deg.skipped is False

    conn.execute("UPDATE daily_runs SET status='failed' WHERE run_date='2026-08-24'")
    conn.commit()
    failed = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert failed.skipped is False
    assert failed.status == "complete"

    conn.execute("UPDATE daily_runs SET status='running' WHERE run_date='2026-08-24'")
    conn.commit()
    running = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert running.skipped is False
    assert running.status == "complete"


def test_first_run_writes_config_never_overwrite(
    tmp_home, tmp_path, frozen_clock, monkeypatch
):
    isolate(tmp_home, tmp_path, monkeypatch)
    cfg = tmp_home / ".config" / "foreshadow" / "config.toml"
    assert not cfg.exists()
    gh, _ = mini_github()
    run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert cfg.exists()
    cfg.write_text(
        cfg.read_text(encoding="utf-8").replace("star_min = 50", "star_min = 99")
    )
    run_pipeline(clock=frozen_clock, force=True, llm=False, client=gh)
    assert "star_min = 99" in cfg.read_text(encoding="utf-8")


def test_cli_run_empty_exit_0(tmp_home, tmp_path, frozen_clock, monkeypatch):
    isolate(tmp_home, tmp_path, monkeypatch)
    gh, _ = mini_github()
    monkeypatch.setattr(
        "foreshadow.github.client.GitHubClient",
        lambda *a, **k: gh,
    )
    result = CliRunner().invoke(app, ["run", "--date", "2026-08-24"])
    assert result.exit_code == 0
    assert "Foreshadow 2026-08-24" in result.stdout
    assert "selected 0" in result.stdout
    assert "report:" in result.stdout
    assert "v7" in (tmp_home / "reports" / "2026-08-24.md").read_text(encoding="utf-8")


def test_cli_run_degraded_exit_0(tmp_home, tmp_path, monkeypatch):
    isolate(tmp_home, tmp_path, monkeypatch)
    gh, _ = mini_github()
    gh.search_total_override = 400
    monkeypatch.setattr(
        "foreshadow.github.client.GitHubClient",
        lambda *a, **k: gh,
    )
    result = CliRunner().invoke(app, ["run", "--date", "2026-08-24"])
    assert result.exit_code == 0
    assert "degraded" in result.stdout


def test_cli_report_and_show(tmp_home, tmp_path, frozen_clock, monkeypatch):
    isolate(tmp_home, tmp_path, monkeypatch)
    gh, _ = mini_github("acme/toy", "R_toy")
    run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    runner = CliRunner()
    md = runner.invoke(app, ["report", "--date", "2026-08-24"])
    assert md.exit_code == 0
    assert "# Foreshadow — 2026-08-24" in md.stdout
    js = runner.invoke(app, ["report", "--date", "2026-08-24", "--json"])
    assert js.exit_code == 0
    payload = json.loads(js.stdout)
    assert list(payload) == list(REPORT_KEYS)
    shown = runner.invoke(app, ["show", "acme/toy"])
    assert shown.exit_code == 0
    assert "acme/toy" in shown.stdout
    assert gh.hydrate_calls > 0
    calls = gh.hydrate_calls
    shown2 = runner.invoke(app, ["show", "acme/toy"])
    assert shown2.exit_code == 0
    assert gh.hydrate_calls == calls


def test_show_unknown_exits_2_without_hydrate(tmp_home, tmp_path, monkeypatch):
    isolate(tmp_home, tmp_path, monkeypatch)
    gh, _ = mini_github()
    monkeypatch.setattr(
        "foreshadow.github.client.GitHubClient",
        lambda *a, **k: gh,
    )
    result = CliRunner().invoke(app, ["show", "nope/unknown"])
    assert result.exit_code == 2
    assert gh.hydrate_calls == 0


def test_run_pipeline_replaces_scores_not_reviews(
    tmp_home, tmp_path, frozen_clock, monkeypatch
):
    isolate(tmp_home, tmp_path, monkeypatch)
    gh, _ = mini_github()
    run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    repo_id = conn.execute("SELECT id FROM repos WHERE node_id='R_toy'").fetchone()[0]
    run_id = conn.execute("SELECT id FROM daily_runs").fetchone()[0]
    conn.execute(
        "INSERT INTO reviews(repo_id, action, note, run_id, created_at) VALUES (?,?,?,?,?)",
        (repo_id, "watch", None, run_id, frozen_clock.now().isoformat()),
    )
    conn.commit()
    run_pipeline(clock=frozen_clock, force=True, llm=False, client=gh)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    assert conn.execute("SELECT COUNT(*) FROM daily_runs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0] >= 1


def _crash_after_hydrate(
    tmp_home, tmp_path, frozen_clock, monkeypatch, exc: BaseException
):
    isolate(tmp_home, tmp_path, monkeypatch)
    gh, _ = mini_github()
    from foreshadow.pipeline.score import score_repo as real_score

    calls = {"n": 0}

    def boom(*args, **kwargs):
        if calls["n"] == 0:
            calls["n"] += 1
            raise exc
        return real_score(*args, **kwargs)

    monkeypatch.setattr("foreshadow.pipeline.score_repo", boom)
    with pytest.raises(type(exc)):
        run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    status = conn.execute("SELECT status FROM daily_runs").fetchone()[0]
    assert status not in {"complete", "degraded"}
    assert not (tmp_home / "reports" / "2026-08-24.md").exists()
    recovered = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert recovered.skipped is False
    assert recovered.status in {"complete", "degraded"}
    assert recovered.report_path is not None
    assert Path(recovered.report_path).is_file()


def test_score_crash_after_hydrate_does_not_skip(
    tmp_home, tmp_path, frozen_clock, monkeypatch
):
    _crash_after_hydrate(
        tmp_home, tmp_path, frozen_clock, monkeypatch, RuntimeError("score failed")
    )


def test_keyboard_interrupt_after_hydrate_does_not_skip(
    tmp_home, tmp_path, frozen_clock, monkeypatch
):
    _crash_after_hydrate(
        tmp_home, tmp_path, frozen_clock, monkeypatch, KeyboardInterrupt()
    )


def test_failed_and_not_found_are_not_scored_as_today(
    tmp_home, tmp_path, frozen_clock, monkeypatch
):
    isolate(tmp_home, tmp_path, monkeypatch)
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    ok = repo_node("R_ok", "acme/ok", stargazerCount=120)
    fail = repo_node("R_fail", "acme/fail", stargazerCount=900)
    gone = repo_node("R_gone", "acme/gone", stargazerCount=400)
    rid_fail = seed_repo(conn, "R_fail", "acme/fail")
    rid_gone = seed_repo(conn, "R_gone", "acme/gone")
    seed_review(conn, rid_fail, "watch", "2026-08-23T00:00:00+00:00")
    seed_review(conn, rid_gone, "watch", "2026-08-23T00:00:01+00:00")
    from foreshadow.pipeline.snapshot import upsert_snapshot

    prior = {
        "stars": 900,
        "forks": 10,
        "open_issues": 1,
        "open_prs": 0,
        "last_pushed_at": "2026-08-20T00:00:00Z",
        "created_at": "2026-05-01T00:00:00Z",
        "captured_at": "2026-08-23T00:05:00+00:00",
        "topics_json": "[]",
        "features_json": "{}",
    }
    upsert_snapshot(conn, rid_fail, "2026-08-23", prior)
    upsert_snapshot(conn, rid_gone, "2026-08-23", {**prior, "stars": 400})
    conn.commit()
    gh = FakeGitHub(
        nodes={"R_ok": ok, "R_fail": fail, "R_gone": gone},
        search_nodes=[ok],
        fail_ids={"R_fail"},
        missing={"R_gone"},
    )
    result = run_pipeline(clock=frozen_clock, force=False, llm=False, client=gh)
    assert result.status == "degraded"
    conn = connect(tmp_home / "foreshadow.sqlite3")
    names = {
        row[0]
        for row in conn.execute(
            """
            SELECT r.full_name FROM scores s
            JOIN repos r ON r.id = s.repo_id
            """
        )
    }
    assert "acme/ok" in names
    assert "acme/fail" not in names
    assert not any(n.startswith("acme/gone") for n in names)
    statuses = {
        row[0]: row[1]
        for row in conn.execute(
            """
            SELECT r.node_id, c.hydrate_status
            FROM candidates c JOIN repos r ON r.id = c.repo_id
            """
        )
    }
    assert statuses["R_fail"] == "failed"
    assert statuses["R_gone"] == "not_found"
    assert statuses["R_ok"] in {"ok", "incomplete"}
    today_fail = conn.execute(
        """
        SELECT stars FROM snapshots
        WHERE repo_id=? AND snapshot_date='2026-08-24'
        """,
        (rid_fail,),
    ).fetchone()
    assert today_fail is None


def test_cli_run_redacts_exception_token(tmp_home, tmp_path, monkeypatch):
    isolate(tmp_home, tmp_path, monkeypatch)

    def boom(*_a, **_k):
        raise RuntimeError("token ghp_abcdefghijklmnopqrstuvwxyz012345 leaked")

    monkeypatch.setattr("foreshadow.cli.run_pipeline", boom)
    result = CliRunner().invoke(app, ["run", "--date", "2026-08-24"])
    assert result.exit_code == 1
    blob = f"{result.stdout}{result.stderr}{result.output}"
    assert "ghp_" not in blob
    assert "[REDACTED]" in blob
