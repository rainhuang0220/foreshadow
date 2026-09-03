from foreshadow.pipeline.star_trust import star_trust


def test_default_trust_is_one():
    assert star_trust(None, None, None, None, None, None, None) == 1.0
    assert star_trust(100, 20, 10, 8, 2.0, 1.5, None) == 1.0


def test_isolation_damps_huge_stars():
    damped = star_trust(10_000, 1, 0, 1, None, None, None)
    healthy = star_trust(100, 20, 10, 8, None, None, None)
    assert 0.3 <= damped < 1.0
    assert healthy == 1.0
    assert damped < healthy


def test_burst_v7_over_v30_damps():
    damped = star_trust(100, 20, 10, 8, 50.0, 2.0, None)
    steady = star_trust(100, 20, 10, 8, 2.0, 1.5, None)
    assert 0.3 <= damped < 1.0
    assert damped < steady


def test_h_flags_damp_fake_growth():
    base = star_trust(100, 20, 10, 8, 2.0, 1.5, None)
    h1 = star_trust(100, 20, 10, 8, 2.0, 1.5, ["H1"])
    h7 = star_trust(100, 20, 10, 8, 2.0, 1.5, ["H7"])
    fake = star_trust(100, 20, 10, 8, 2.0, 1.5, ["fake-growth"])
    assert 0.3 <= h1 < base
    assert 0.3 <= h7 < base
    assert 0.3 <= fake < base


def test_star_trust_stays_in_range():
    extreme = star_trust(1_000_000, 0, 0, 0, 100.0, 0.1, ["H1", "H7"])
    assert 0.3 <= extreme <= 1.0
