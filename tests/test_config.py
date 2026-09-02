import pytest

from foreshadow.config import load_config


def test_default_weights_sum_to_100(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text("# isolated defaults\n")
    monkeypatch.setenv("FORESHADOW_CONFIG", str(cfg))
    s = load_config(cwd=tmp_path)
    w = s.scoring
    assert (
        w.momentum_weight
        + w.real_user_weight
        + w.gap_weight
        + w.contribution_opp_weight
        + w.early_entry_weight
        + w.direction_fit_weight
        + w.maintainer_weight
        == 100
    )
    assert w.momentum_weight == 20
    assert w.real_user_weight == 15
    assert w.gap_weight == 15
    assert w.contribution_opp_weight == 20
    assert w.early_entry_weight == 15
    assert w.direction_fit_weight == 10
    assert w.maintainer_weight == 5
    assert s.github.hydrate_concurrency == 6


def test_fractional_weights_exit_2(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[scoring]\nmomentum_weight = 0.20\nreal_user_weight = 15\ngap_weight = 15\ncontribution_opp_weight = 20\nearly_entry_weight = 15\ndirection_fit_weight = 10\nmaintainer_weight = 5\n"
    )
    monkeypatch.setenv("FORESHADOW_CONFIG", str(cfg))
    with pytest.raises(SystemExit) as ei:
        load_config(cwd=tmp_path)
    assert ei.value.code == 2


def test_does_not_overwrite_existing_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[discovery]\nstar_min = 99\n")
    monkeypatch.setenv("FORESHADOW_CONFIG", str(cfg))
    # first-run helper must not overwrite
    from foreshadow.config import ensure_default_config

    ensure_default_config(cfg)
    assert "star_min = 99" in cfg.read_text()
