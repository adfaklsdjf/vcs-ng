"""Tests for directory scanning, existing-output classification, and -r CLI mode."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest
from PIL import Image

from vcsng.cli import main
from vcsng.config import DEFAULT_EXTENSIONS, build_settings, parse_extensions
from vcsng.errors import OutputError, UsageError
from vcsng.scan import Existing, check_existing, iter_videos, set_aside


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


# --- iter_videos ----------------------------------------------------------

def test_iter_videos_finds_and_skips(tmp_path):
    keep = [
        _touch(tmp_path / "a.mkv"),
        _touch(tmp_path / "Show" / "S01" / "ep1.MP4"),
        _touch(tmp_path / "Show" / "resampled.avi"),
    ]
    _touch(tmp_path / "notes.txt")
    _touch(tmp_path / "a.jpg")
    _touch(tmp_path / ".hidden.mkv")
    _touch(tmp_path / ".cache" / "b.mkv")
    _touch(tmp_path / "Movie" / "movie-sample.mkv")
    _touch(tmp_path / "Movie" / "Sample" / "clip.mkv")
    (tmp_path / "link.mkv").symlink_to(tmp_path / "a.mkv")
    (tmp_path / "linkdir").symlink_to(tmp_path / "Show")

    found = list(iter_videos(tmp_path, DEFAULT_EXTENSIONS))
    assert sorted(found) == sorted(keep)


def test_iter_videos_custom_extensions(tmp_path):
    _touch(tmp_path / "a.mkv")
    ts = _touch(tmp_path / "b.ts")
    assert list(iter_videos(tmp_path, ("ts",))) == [ts]


# --- extensions setting ---------------------------------------------------

def test_parse_extensions_normalizes():
    assert parse_extensions([".MKV", "mp4", " webm "]) == ("mkv", "mp4", "webm")
    assert parse_extensions("mkv,.TS") == ("mkv", "ts")


def test_parse_extensions_rejects_empty_and_bad():
    with pytest.raises(UsageError):
        parse_extensions([])
    with pytest.raises(UsageError):
        parse_extensions([1, 2])


def test_scan_section_from_config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[scan]\nextensions = ["mkv", ".MP4"]\nmin_width = 1500\n')
    s = build_settings({}, config_path=cfg)
    assert s.extensions == ("mkv", "mp4")
    assert s.min_width == 1500


def test_scan_defaults():
    s = build_settings({}, no_config=True)
    assert s.min_width is None
    assert s.regenerate is False
    assert "mkv" in s.extensions and "webm" in s.extensions


# --- check_existing / set_aside --------------------------------------------

def test_check_existing_missing(tmp_path):
    assert check_existing(tmp_path / "x.jpg", "jpeg", 2000) == (Existing.MISSING, None)


@pytest.mark.parametrize("fmt,ext", [("jpeg", "jpg"), ("png", "png")])
def test_check_existing_width(tmp_path, fmt, ext):
    p = tmp_path / f"x.{ext}"
    Image.new("RGB", (2100, 10)).save(p, format=fmt.upper())
    assert check_existing(p, fmt, 2000) == (Existing.OK, 2100)
    assert check_existing(p, fmt, 2200) == (Existing.UNDERSIZED, 2100)
    assert check_existing(p, fmt, None) == (Existing.OK, 2100)


def test_check_existing_wrong_format_is_bad(tmp_path):
    p = tmp_path / "x.jpg"
    Image.new("RGB", (2100, 10)).save(p, format="PNG")
    assert check_existing(p, "jpeg", 2000)[0] is Existing.BAD


@pytest.mark.parametrize("fmt,ext", [("jpeg", "jpg"), ("png", "png")])
def test_check_existing_truncated_is_bad(tmp_path, fmt, ext):
    p = tmp_path / f"x.{ext}"
    Image.effect_noise((2100, 200), 50).convert("RGB").save(p, format=fmt.upper())
    data = p.read_bytes()
    p.write_bytes(data[: len(data) // 2])
    assert check_existing(p, fmt, 2000)[0] is Existing.BAD


def test_check_existing_junk_is_bad(tmp_path):
    p = tmp_path / "x.jpg"
    p.write_text("definitely not an image")
    assert check_existing(p, "jpeg", 2000) == (Existing.BAD, None)


def test_check_existing_directory_raises(tmp_path):
    (tmp_path / "x.jpg").mkdir()
    with pytest.raises(OutputError):
        check_existing(tmp_path / "x.jpg", "jpeg", 2000)


def test_set_aside_numbers_collisions(tmp_path):
    p = tmp_path / "x.jpg"
    p.write_text("one")
    assert set_aside(p) == tmp_path / "x.jpg.bad"
    p.write_text("two")
    assert set_aside(p) == tmp_path / "x.jpg.bad-1"
    assert (tmp_path / "x.jpg.bad").read_text() == "one"
    assert (tmp_path / "x.jpg.bad-1").read_text() == "two"
    assert not p.exists()


# --- CLI ------------------------------------------------------------------

def test_cli_requires_input_without_r(capsys):
    with pytest.raises(SystemExit):
        main(["--no-config"])
    assert "no input files" in capsys.readouterr().err


@pytest.mark.ffmpeg
def test_cli_recursive_scan(synthetic_video, tmp_path, monkeypatch, caplog):
    root = tmp_path / "media"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    shutil.copy(synthetic_video, root / "a" / "good.mp4")
    shutil.copy(synthetic_video, root / "a" / "small.mp4")
    shutil.copy(synthetic_video, root / "b" / "junk.mp4")
    shutil.copy(synthetic_video, root / "b" / "corrupt.mp4")
    shutil.copy(synthetic_video, root / "b" / "new.mp4")
    (root / "b" / "broken.mp4").write_bytes(b"not a video")

    Image.new("RGB", (5000, 10)).save(root / "a" / "good-ss.jpg", format="JPEG")
    Image.new("RGB", (300, 10)).save(root / "a" / "small-ss.jpg", format="JPEG")
    (root / "b" / "junk-ss.jpg").write_text("??")
    Image.effect_noise((900, 200), 50).convert("RGB").save(
        root / "b" / "corrupt-ss.jpg", format="JPEG"
    )
    data = (root / "b" / "corrupt-ss.jpg").read_bytes()
    (root / "b" / "corrupt-ss.jpg").write_bytes(data[: len(data) // 2])

    monkeypatch.chdir(tmp_path)  # sheets must land next to videos, not in CWD
    args = ["--no-config", "-n", "2", "-f", "jpeg", "--suffix=-ss", "--min-width", "600"]
    with caplog.at_level(logging.INFO, logger="vcsng"):
        rc = main([*args, str(root)])

    assert rc != 0  # broken.mp4 failed
    assert "is a directory; scanning recursively" in caplog.text
    # untouched: already wide enough
    assert Image.open(root / "a" / "good-ss.jpg").width == 5000
    # regenerated; the old one is kept as -old
    assert Image.open(root / "a" / "small-ss.jpg").width >= 600
    assert Image.open(root / "a" / "small-ss-old.jpg").width == 300
    # junk and corrupt set aside, then regenerated
    assert (root / "b" / "junk-ss.jpg.bad").read_text() == "??"
    assert (root / "b" / "corrupt-ss.jpg.bad").exists()
    for name in ("junk-ss.jpg", "corrupt-ss.jpg", "new-ss.jpg"):
        assert check_existing(root / "b" / name, "jpeg", 600)[0] is Existing.OK
    assert not list(tmp_path.glob("*.jpg"))
    # summary + failure list at the end
    assert "1 generated, 3 regenerated, 1 up to date, 1 failed" in caplog.text
    tail = caplog.text[caplog.text.index("failed (1):"):]
    assert "broken.mp4" in tail

    # second run with -r from inside the tree: everything is up to date
    caplog.clear()
    monkeypatch.chdir(root)
    with caplog.at_level(logging.INFO, logger="vcsng"):
        main([*args, "-r"])
    assert "0 generated" not in caplog.text
    assert "5 up to date, 1 failed" in caplog.text


def _scan_tree(synthetic_video, root: Path) -> None:
    root.mkdir()
    shutil.copy(synthetic_video, root / "small.mp4")
    shutil.copy(synthetic_video, root / "new.mp4")
    Image.new("RGB", (300, 10)).save(root / "small-ss.jpg", format="JPEG")


_SCAN_ARGS = ["--no-config", "-n", "2", "-f", "jpeg", "--suffix=-ss"]


@pytest.mark.ffmpeg
def test_cli_scan_without_min_width_keeps_any_valid_sheet(synthetic_video, tmp_path, caplog):
    root = tmp_path / "media"
    _scan_tree(synthetic_video, root)
    with caplog.at_level(logging.INFO, logger="vcsng"):
        assert main([*_SCAN_ARGS, str(root)]) == 0
    assert Image.open(root / "small-ss.jpg").width == 300
    assert (root / "new-ss.jpg").exists()
    assert not (root / "small-ss-old.jpg").exists()
    assert "generating 1 contact sheet (1 new, 1 up to date)" in caplog.text
    assert "1 generated, 1 up to date, 0 failed" in caplog.text


@pytest.mark.ffmpeg
def test_cli_scan_regenerate_renames_old(synthetic_video, tmp_path, caplog):
    root = tmp_path / "media"
    _scan_tree(synthetic_video, root)
    with caplog.at_level(logging.INFO, logger="vcsng"):
        assert main([*_SCAN_ARGS, "--regenerate", str(root)]) == 0
    assert Image.open(root / "small-ss.jpg").width > 300
    assert Image.open(root / "small-ss-old.jpg").width == 300
    assert "generating 2 contact sheets (1 new, 1 replacing existing)" in caplog.text
    assert "1 generated, 1 regenerated, 0 failed" in caplog.text


@pytest.mark.ffmpeg
def test_cli_scan_regenerate_overwrite_clobbers(synthetic_video, tmp_path):
    root = tmp_path / "media"
    _scan_tree(synthetic_video, root)
    assert main([*_SCAN_ARGS, "--regenerate", "--overwrite", str(root)]) == 0
    assert Image.open(root / "small-ss.jpg").width > 300
    assert sorted(p.name for p in root.glob("*.jpg")) == ["new-ss.jpg", "small-ss.jpg"]
