from datetime import date, timedelta

from foreshadow.clock import Clock
from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.features import (
    SnapshotPoint,
    clip01,
    compute_windows,
    is_readme_only_blob,
    is_readme_only_tree,
    readme_install,
    screenshot_only,
    star_velocity,
)


def test_clip01():
    assert clip01(-1) == 0
    assert clip01(0.5) == 0.5
    assert clip01(2) == 1


def test_v7_nearest_slack():
    t = date(2026, 8, 24)
    snaps = [
        SnapshotPoint(date(2026, 8, 24), 900, 85, None),
        SnapshotPoint(date(2026, 8, 18), 400, 40, None),  # t-6
        SnapshotPoint(date(2026, 8, 16), 200, 18, None),  # t-8
    ]
    v, src = star_velocity(snaps, t, 7, slack_days=1)
    assert src == "nearest-1d"
    assert abs(v - (900 - 200) / 7) < 1e-6


def test_v7_too_old_is_na():
    t = date(2026, 8, 24)
    snaps = [
        SnapshotPoint(date(2026, 8, 24), 900, 85, None),
        SnapshotPoint(date(2026, 8, 15), 200, 18, None),  # t-9
    ]
    v, src = star_velocity(snaps, t, 7, slack_days=1)
    assert v is None and src is None


def test_install_verb():
    assert readme_install("# x\n\npip install memkit\n") == 1
    assert readme_install("# pretty\n![a](a.gif)\n![b](b.gif)\n") == 0


def test_gemfile_only_is_not_h3():
    assert is_readme_only_tree(["README.md", "Gemfile"]) is False
    assert is_readme_only_tree(["README.md", "LICENSE", ".gitignore"]) is True
    # 12.C tree (README + one app.py) is not H3
    assert is_readme_only_tree(["README.md", "app.py"]) is False


def test_v7_exact_beats_slack_neighbor():
    t = date(2026, 8, 24)
    snaps = [
        SnapshotPoint(t, 900, 85, None),
        SnapshotPoint(t - timedelta(days=7), 200, 18, None),
        SnapshotPoint(t - timedelta(days=8), 150, 10, None),
    ]
    v, src = star_velocity(snaps, t, 7, slack_days=1)
    assert src == "exact"
    assert v == (900 - 200) / 7


def test_v7_missing_today_is_na_not_zero():
    t = date(2026, 8, 24)
    snaps = [SnapshotPoint(t - timedelta(days=7), 200, 18, None)]
    v, src = star_velocity(snaps, t, 7, slack_days=1)
    assert v is None and src is None


def test_negative_velocity_is_not_missing():
    t = date(2026, 8, 24)
    snaps = [
        SnapshotPoint(t, 180, 10, None),
        SnapshotPoint(t - timedelta(days=7), 200, 18, None),
    ]
    v, src = star_velocity(snaps, t, 7, slack_days=1)
    assert src == "exact"
    assert v == (180 - 200) / 7


def test_compute_windows_memkit(frozen_clock: Clock):
    t = frozen_clock.today()
    snaps = [
        SnapshotPoint(t, 900, 85, None),
        SnapshotPoint(t - timedelta(days=7), 200, 18, None),
        SnapshotPoint(t - timedelta(days=30), 180, 12, None),
    ]
    windows = compute_windows(
        snaps,
        frozen_clock,
        created_at=t - timedelta(days=75),
        slack_days=1,
    )
    assert windows.v7 == 100.0
    assert windows.v30 == 24.0
    assert windows.v90 is None
    assert windows.v7_source == "exact"
    assert windows.v30_source == "exact"
    assert windows.v90_source is None
    assert abs(windows.rel_growth_7d - 3.5) < 1e-6
    assert abs(windows.accel_ratio - (100 / 24)) < 1e-6
    assert windows.lifetime_star_rate == 900 / 75
    assert windows.is_accelerating is True


def test_compute_windows_v30_na_no_impute(frozen_clock: Clock):
    t = frozen_clock.today()
    snaps = [
        SnapshotPoint(t, 900, 85, None),
        SnapshotPoint(t - timedelta(days=7), 200, 18, None),
    ]
    windows = compute_windows(
        snaps,
        frozen_clock,
        created_at=t - timedelta(days=75),
        slack_days=1,
    )
    assert windows.v7 == 100.0
    assert windows.v30 is None
    assert windows.accel_ratio is None
    assert windows.v7_source == "exact"
    assert windows.lifetime_star_rate == 900 / 75
    assert windows.is_accelerating is True


def test_younger_than_n_window_is_na(frozen_clock: Clock):
    t = frozen_clock.today()
    snaps = [
        SnapshotPoint(t, 50, 1, None),
        SnapshotPoint(t - timedelta(days=7), 10, 0, None),
    ]
    windows = compute_windows(
        snaps,
        frozen_clock,
        created_at=t - timedelta(days=5),
        slack_days=1,
    )
    assert windows.v7 is None
    assert windows.v7_source is None
    assert windows.rel_growth_7d is None
    assert windows.lifetime_star_rate == 50 / 5


def test_giant_not_accelerating(frozen_clock: Clock):
    t = frozen_clock.today()
    snaps = [
        SnapshotPoint(t, 100_000, 22_000, None),
        SnapshotPoint(t - timedelta(days=7), 99_650, 21_923, None),
        SnapshotPoint(t - timedelta(days=30), 98_500, 21_670, None),
    ]
    windows = compute_windows(
        snaps,
        frozen_clock,
        created_at=t - timedelta(days=4_000),
        slack_days=1,
    )
    assert windows.v7 == 50.0
    assert abs(windows.rel_growth_7d - (350 / 99_650)) < 1e-9
    assert windows.is_accelerating is False


def test_curl_pipe_bash_is_install():
    assert readme_install("curl https://example.com/install.sh | bash\n") == 1
    assert readme_install("curl -fsSL https://x | sh\n") == 1


def test_screenshot_only_pretty_gifs():
    text = "# pretty\n![a](a.gif)\n![b](b.gif)\n"
    assert screenshot_only(text) is True
    assert readme_install(text) == 0


def test_screenshot_only_rejects_language_fence():
    text = "# pretty\n![a](a.gif)\n![b](b.png)\n\n```python\nprint('hi')\n```\n"
    assert screenshot_only(text) is False


def test_screenshot_only_html_images():
    text = '<img src="a.webp"><img src="b.svg">'
    assert screenshot_only(text) is True


def test_tree_source_dir_and_single_file():
    assert is_readme_only_tree(["README.md", "src"]) is False
    # 12.C README + app.py is not H3; any source file disqualifies README-only
    assert is_readme_only_tree(["README.md", "hello.py"]) is False
    assert is_readme_only_tree(["README.md", "a.py", "b.rs"]) is False
    assert is_readme_only_tree(["README.md", "COPYING", ".gitattributes"]) is True


def test_missing_tree_names_is_na_not_h3():
    assert is_readme_only_blob(FeaturesBlob()) is None
    assert (
        is_readme_only_blob(
            FeaturesBlob(tree_names=["README.md", "LICENSE", ".gitignore"])
        )
        is True
    )
    assert (
        is_readme_only_blob(FeaturesBlob(tree_names=["README.md", "Gemfile"])) is False
    )
