from fractions import Fraction
from pathlib import Path

import pytest

from vcsng.config import Settings, build_settings, load_config_file, profile_path
from vcsng.errors import UsageError
from vcsng.values import Percent


def write_toml(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def test_precedence_defaults_only():
    s = build_settings({}, no_config=True)
    assert s == Settings()


def test_precedence_config_then_profile_then_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = write_toml(
        tmp_path / "config.toml",
        "[layout]\ncolumns = 3\n\n[output]\nformat = \"jpg\"\n",
    )
    profile_dir = tmp_path / "xdg" / "vcsng" / "profiles"
    profile_dir.mkdir(parents=True)
    write_toml(profile_dir / "myprofile.toml", "[layout]\ncolumns = 5\n")

    s = build_settings(
        {"columns": 7},
        config_path=config,
        profiles=("myprofile",),
    )
    assert s.columns == 7  # cli wins
    assert s.format == "jpeg"  # from config, jpg -> jpeg

    s2 = build_settings({}, config_path=config, profiles=("myprofile",))
    assert s2.columns == 5  # profile beats config

    s3 = build_settings({}, config_path=config)
    assert s3.columns == 3  # config beats defaults


def test_bg_all_expansion_specific_key_wins_same_layer(tmp_path):
    config = write_toml(
        tmp_path / "config.toml",
        '[style]\nbg_all = "black"\nbg_heading = "red"\n',
    )
    s = build_settings({}, config_path=config)
    assert s.bg_heading == "red"
    assert s.bg_sign == "black"
    assert s.bg_title == "black"
    assert s.bg_contact == "black"
    assert s.bg_tstamps == "black"


def test_fg_all_and_font_all_expansion(tmp_path):
    config = write_toml(
        tmp_path / "config.toml",
        '[style]\nfg_all = "white"\nfont_all = "Arial"\n',
    )
    s = build_settings({}, config_path=config)
    assert s.fg_heading == "white"
    assert s.fg_sign == "white"
    assert s.fg_title == "white"
    assert s.fg_tstamps == "white"
    assert s.font_heading == "Arial"
    assert s.font_tstamps == "Arial"
    assert s.font_sign == "Arial"
    assert s.font_title == "Arial"


def test_mode_inference_from_interval_key(tmp_path):
    config = write_toml(tmp_path / "config.toml", "[capture]\ninterval = \"20s\"\n")
    s = build_settings({}, config_path=config)
    assert s.mode == "interval"
    assert s.interval == 20.0


def test_mode_inference_from_numcaps_key(tmp_path):
    config = write_toml(tmp_path / "config.toml", "[capture]\nnumcaps = 30\n")
    s = build_settings({}, config_path=config)
    assert s.mode == "numcaps"


def test_explicit_mode_wins_over_inference(tmp_path):
    config = write_toml(
        tmp_path / "config.toml",
        '[capture]\nmode = "manual"\ninterval = "20s"\n',
    )
    s = build_settings({}, config_path=config)
    assert s.mode == "manual"


def test_format_jpg_normalized_to_jpeg(tmp_path):
    config = write_toml(tmp_path / "config.toml", '[output]\nformat = "jpg"\n')
    s = build_settings({}, config_path=config)
    assert s.format == "jpeg"


def test_format_invalid_raises(tmp_path):
    config = write_toml(tmp_path / "config.toml", '[output]\nformat = "gif"\n')
    with pytest.raises(UsageError):
        build_settings({}, config_path=config)


def test_unknown_key_warning(tmp_path, caplog):
    config = write_toml(tmp_path / "config.toml", "[layout]\nnonexistent_key = 5\n")
    with caplog.at_level("WARNING"):
        build_settings({}, config_path=config)
    assert "unknown key" in caplog.text
    assert "nonexistent_key" in caplog.text


def test_unknown_section_ignored(tmp_path, caplog):
    config = write_toml(tmp_path / "config.toml", "[bogus]\nfoo = 1\n")
    with caplog.at_level("WARNING"):
        s = build_settings({}, config_path=config)
    assert "unknown section" in caplog.text
    assert s == Settings()


def test_profile_not_found_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    with pytest.raises(UsageError):
        build_settings({}, no_config=True, profiles=("doesnotexist",))


def test_builtin_profile_black(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    s = build_settings({}, no_config=True, profiles=("black",))
    assert s.bg_heading == "black"
    assert s.fg_heading == "white"


def test_builtin_profile_compact(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    s = build_settings({}, no_config=True, profiles=("compact",))
    assert s.mode == "numcaps"
    assert s.numcaps == 72
    assert s.columns == 12
    assert s.height == 40
    assert s.padding == 0
    assert s.shadows is False
    assert s.timestamps is False


def test_config_file_not_found_raises(tmp_path):
    missing = tmp_path / "does-not-exist.toml"
    with pytest.raises(UsageError):
        build_settings({}, config_path=missing)


def test_unknown_settings_from_cli_raises():
    with pytest.raises(UsageError):
        build_settings({"not_a_field": 1}, no_config=True)
