from datetime import UTC, datetime, timedelta

import pytest

from fakes import seed_repo
from foreshadow.db import connect, migrate
from foreshadow.entry import analyze_entry, load_entry, persist_entry
from foreshadow.models import FeaturesBlob

NOW = datetime(2026, 9, 1, 0, 5, tzinfo=UTC)


def _cited_issue_ids(strategy) -> set[int]:
    ids: set[int] = set()
    for plan in (strategy.recommended, *strategy.alternatives):
        if plan.issue_number is not None:
            ids.add(int(plan.issue_number))
        if plan.pr_number is not None:
            ids.add(int(plan.pr_number))
        for item in plan.evidence:
            raw = item.get("id")
            if raw is not None:
                ids.add(int(raw))
    return ids


def _routes(strategy) -> list[str]:
    return [strategy.recommended.route, *[p.route for p in strategy.alternatives]]


@pytest.mark.parametrize(
    "text,wants_issue_first,unsolicited,cla,dco",
    [
        pytest.param(
            "Please open an issue first before sending a pull request.",
            True,
            False,
            None,
            None,
            id="issue-first",
        ),
        pytest.param(
            "Discuss first. Unsolicited PRs will be closed.",
            True,
            False,
            None,
            None,
            id="discuss-first",
        ),
        pytest.param(
            "The CLA bot will ask you to sign the contributor license agreement.",
            False,
            False,
            True,
            None,
            id="cla",
        ),
        pytest.param(
            "Commits must include a Signed-off-by trailer (DCO / Developer Certificate of Origin).",
            False,
            False,
            None,
            True,
            id="dco",
        ),
        pytest.param(
            "Open an issue first. CLA bot enforces the contributor license. Signed-off-by required.",
            True,
            False,
            True,
            True,
            id="issue-first-cla-dco",
        ),
    ],
)
def test_culture_heuristics_from_fixture_text(
    text, wants_issue_first, unsolicited, cla, dco
):
    strat = analyze_entry(
        {"contributing": text, "readme_excerpt": text},
        now=NOW,
    )
    assert strat.policy.wants_issue_first is wants_issue_first
    assert strat.policy.unsolicited_pr_ok is unsolicited
    assert strat.policy.cla is cla
    assert strat.policy.dco is dco


def test_readme_issue_first_without_contributing():
    strat = analyze_entry(
        {"readme_excerpt": "Please discuss first; do not open a PR yet."},
        now=NOW,
    )
    assert strat.policy.wants_issue_first is True
    assert strat.policy.unsolicited_pr_ok is False


def test_empty_sample_unknown_policy_no_fake_ids():
    strat = analyze_entry({}, now=NOW)
    assert strat.policy.cla is None
    assert strat.policy.dco is None
    assert strat.policy.good_first_issue_alive is None
    assert strat.recommended.route in {"ISSUE_FIRST", "DOCS"}
    assert strat.recommended.issue_number is None
    assert strat.recommended.pr_number is None
    assert strat.recommended.confidence < 0.4
    assert _cited_issue_ids(strat) == set()
    assert len(strat.alternatives) <= 2
    assert strat.recommended.route not in {p.route for p in strat.alternatives}


def test_counts_without_ids_do_not_invent_issue_numbers():
    strat = analyze_entry(
        {
            "bug_n": 4,
            "help_n": 2,
            "unassigned_help": 2,
            "issue_sample_n": 8,
            "open_issue_titles": ["crash on empty batch", "docs typo"],
        },
        now=NOW,
        language="Python",
    )
    assert strat.recommended.issue_number is None
    assert _cited_issue_ids(strat) == set()


def test_python_help_wanted_open_issue_is_plan_a():
    feat = {
        "language": "Python",
        "full_name": "acme/toy",
        "help_n": 1,
        "unassigned_help": 1,
        "bug_n": 1,
        "issue_sample_n": 3,
        "help_issue_titles": ["#381 crash on empty batch"],
        "open_issue_titles": ["#381 crash on empty batch", "#390 docs nit"],
        "issues": [
            {
                "number": 381,
                "title": "crash on empty batch",
                "state": "OPEN",
                "labels": ["help wanted", "bug"],
                "assignees": [],
                "updatedAt": "2026-08-20T00:00:00Z",
                "url": "https://github.com/acme/toy/issues/381",
            },
            {
                "number": 390,
                "title": "docs nit",
                "state": "OPEN",
                "labels": ["documentation"],
                "updatedAt": "2026-08-18T00:00:00Z",
            },
        ],
        "pr_accept_rate": 0.5,
        "pr_merged_sample_n": 6,
        "pr_review_rate": 0.6,
        "maint_touch": 0.5,
        "tree_names": ["pyproject.toml", "src", "README.md"],
    }
    strat = analyze_entry(feat, now=NOW, language="Python")
    assert strat.recommended.route == "ISSUE"
    assert strat.recommended.issue_number == 381
    assert strat.recommended.confidence >= 0.6
    assert 381 in _cited_issue_ids(strat)
    assert _cited_issue_ids(strat) <= {381, 390}
    assert len(strat.alternatives) == 2
    assert strat.recommended.route not in {p.route for p in strat.alternatives}
    assert len(set(_routes(strat))) == 3
    assert any(
        e.get("kind") == "issue" and e.get("id") == 381
        for e in strat.recommended.evidence
    )


def test_features_blob_help_wanted_uses_title_number():
    blob = FeaturesBlob(
        help_n=1,
        unassigned_help=1,
        bug_n=0,
        issue_sample_n=2,
        help_issue_titles=["#7 typo in README"],
        open_issue_titles=["#7 typo in README"],
        gap_docs=0,
    )
    strat = analyze_entry(blob, now=NOW, language="Python")
    assert strat.recommended.route == "ISSUE"
    assert strat.recommended.issue_number == 7
    assert _cited_issue_ids(strat) <= {7}


def test_rust_low_access_prefers_docs_or_issue_first_over_fix():
    feat = {
        "language": "Rust",
        "pr_accept_rate": 0.05,
        "pr_merged_sample_n": 8,
        "pr_external_merged_n": 0,
        "pr_review_rate": 0.1,
        "maint_touch": 0.1,
        "maint_first_response_hours": 200,
        "gap_docs": 1,
        "tree_names": ["Cargo.toml", "src", "README.md"],
        "todo_hits": ["src/lib.rs: TODO handle cuda error"],
        "open_issue_titles": ["rewrite the inference core"],
    }
    strat = analyze_entry(feat, now=NOW, language="Rust")
    assert strat.recommended.route in {"DOCS", "ISSUE_FIRST"}
    assert strat.recommended.issue_number is None
    assert _cited_issue_ids(strat) == set()
    assert all(p.route != strat.recommended.route for p in strat.alternatives)


def test_good_first_issue_alive_uses_open_and_recency():
    alive = analyze_entry(
        {
            "issues": [
                {
                    "number": 12,
                    "title": "typo",
                    "state": "OPEN",
                    "labels": ["good first issue"],
                    "updatedAt": "2026-08-15T00:00:00Z",
                }
            ]
        },
        now=NOW,
    )
    assert alive.policy.good_first_issue_alive is True
    stale = analyze_entry(
        {
            "issues": [
                {
                    "number": 12,
                    "title": "typo",
                    "state": "OPEN",
                    "labels": ["good-first-issue"],
                    "updatedAt": "2025-01-01T00:00:00Z",
                }
            ]
        },
        now=NOW,
    )
    assert stale.policy.good_first_issue_alive is False


def test_open_pr_claiming_issue_is_skipped_for_plan_a():
    feat = {
        "language": "Python",
        "full_name": "acme/toy",
        "html_url": "https://github.com/acme/toy",
        "help_n": 1,
        "unassigned_help": 1,
        "bug_n": 1,
        "issue_sample_n": 2,
        "tree_names": ["pyproject.toml", "src", "README.md"],
        "pr_accept_rate": 0.5,
        "pr_merged_sample_n": 6,
        "pr_review_rate": 0.6,
        "maint_touch": 0.5,
        "issues": [
            {
                "number": 547,
                "title": "Add Star badge to README top row",
                "state": "OPEN",
                "labels": ["help wanted", "good first issue"],
                "assignees": [],
                "updatedAt": "2026-08-20T00:00:00Z",
                "url": "https://github.com/acme/toy/issues/547",
            },
            {
                "number": 582,
                "title": "stdio crash on non-object JSON",
                "state": "OPEN",
                "labels": ["bug", "security"],
                "assignees": [],
                "updatedAt": "2026-08-21T00:00:00Z",
                "url": "https://github.com/acme/toy/issues/582",
            },
        ],
        "prs": [
            {
                "number": 604,
                "title": "docs: add GitHub Stars badge to README",
                "body": "Fixes #547",
                "url": "https://github.com/acme/toy/pull/604",
            }
        ],
    }
    strat = analyze_entry(feat, now=NOW, language="Python")
    assert strat.recommended.issue_number == 582
    assert 547 not in _cited_issue_ids(strat) or strat.recommended.issue_number != 547
    assert 604 not in {strat.recommended.pr_number}


def test_stale_after_is_three_days():
    strat = analyze_entry({}, now=NOW)
    assert strat.analyzed_at == NOW.isoformat()
    assert strat.stale_after == (NOW + timedelta(days=3)).isoformat()


def test_persist_load_roundtrip(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    rid = seed_repo(conn, "R_toy", "acme/toy")
    feat = {
        "full_name": "acme/toy",
        "help_n": 1,
        "unassigned_help": 1,
        "help_issue_titles": ["#381 crash on empty batch"],
        "issues": [
            {
                "number": 381,
                "title": "crash on empty batch",
                "state": "OPEN",
                "labels": ["help wanted"],
                "assignees": [],
                "updatedAt": "2026-08-20T00:00:00Z",
            }
        ],
        "language": "Python",
        "contributing": "Please open an issue first. CLA bot / contributor license.",
    }
    original = analyze_entry(feat, now=NOW, language="Python")
    persist_entry(conn, rid, original)
    loaded = load_entry(conn, rid)
    assert loaded is not None
    assert loaded.recommended.route == original.recommended.route
    assert loaded.recommended.issue_number == original.recommended.issue_number
    assert loaded.recommended.confidence == pytest.approx(
        original.recommended.confidence
    )
    assert loaded.policy.wants_issue_first is original.policy.wants_issue_first
    assert loaded.policy.cla is original.policy.cla
    assert loaded.analyzed_at == original.analyzed_at
    assert loaded.stale_after == original.stale_after
    assert [p.route for p in loaded.alternatives] == [
        p.route for p in original.alternatives
    ]
    later = analyze_entry({}, now=NOW + timedelta(hours=1))
    persist_entry(conn, rid, later)
    again = load_entry(conn, rid)
    assert again is not None
    assert again.recommended.route == later.recommended.route
    assert again.analyzed_at == later.analyzed_at
    assert load_entry(conn, rid + 99) is None
