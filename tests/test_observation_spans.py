from foreshadow.observation_view import star_delta


def test_sparse_samples_do_not_claim_a_complete_seven_day_window():
    series = [{"date": f"2026-09-{d:02}", "stars": d} for d in (1, 3, 5, 7, 9, 11, 13)]
    delta = star_delta(series)
    assert delta["window_complete"] is False
    assert delta["calendar_days"] == 13
    assert delta["observed_points"] == 7
    assert delta["delta"] == 12


def test_unordered_measurements_use_real_dates_not_input_order():
    delta = star_delta(
        [{"date": "2026-10-03", "stars": 20}, {"date": "2026-10-01", "stars": 10}]
    )
    assert delta["delta"] == 10
    assert delta["first_date"] == "2026-10-01"
    assert delta["last_date"] == "2026-10-03"
    assert delta["calendar_days"] == 3


def test_null_duplicate_and_invalid_measurements_fail_closed():
    delta = star_delta(
        [{"date": "2026-10-01", "stars": None}, {"date": "2026-10-03", "stars": 20}]
    )
    assert delta["pending"] is True
    assert delta["observed_points"] == 1
    for series in (
        [{"date": "bad", "stars": 1}, {"date": "2026-10-03", "stars": 3}],
        [{"date": "2026-10-03", "stars": 1}, {"date": "2026-10-03", "stars": 3}],
    ):
        assert star_delta(series)["pending"] is True
