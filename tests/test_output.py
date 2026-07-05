"""Tests for output.py: template expansion, safe-rename, JPEG flatten."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from vcsng.config import Settings
from vcsng.errors import UsageError
from vcsng.output import resolve_output_path, save_sheet


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


def test_resolve_output_path_default_template(tmp_path):
    s = _settings(format="png")
    result = resolve_output_path(Path("movie.mkv"), s)
    assert result.name == "movie.png"


def test_resolve_output_path_tokens(tmp_path):
    s = _settings(format="jpeg", output="{dir}/{stem}-thumb.{ext}")
    input_path = tmp_path / "clip.mp4"
    result = resolve_output_path(input_path, s)
    assert result == tmp_path / "clip-thumb.jpg"


def test_resolve_output_path_name_token(tmp_path):
    s = _settings(format="png", output="{name}.contact.{ext}")
    result = resolve_output_path(Path("video.mp4"), s)
    assert result.name == "video.mp4.contact.png"


def test_resolve_output_path_unknown_token_raises():
    s = _settings(output="{bogus}.{ext}")
    with pytest.raises(UsageError):
        resolve_output_path(Path("movie.mkv"), s)


def test_resolve_output_path_relative_resolves_against_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = _settings(format="png", output="out/{stem}.{ext}")
    result = resolve_output_path(Path("movie.mkv"), s)
    assert result == tmp_path / "out" / "movie.png"


def _tiny_image(mode="RGB", color=(255, 0, 0)) -> Image.Image:
    return Image.new(mode, (4, 4), color)


def test_save_sheet_safe_rename_sequence(tmp_path):
    target = tmp_path / "sheet.png"
    s = _settings(format="png", overwrite=False)

    p1 = save_sheet(_tiny_image(), target, s)
    assert p1 == target

    p2 = save_sheet(_tiny_image(), target, s)
    assert p2 == tmp_path / "sheet-1.png"

    p3 = save_sheet(_tiny_image(), target, s)
    assert p3 == tmp_path / "sheet-2.png"

    assert p1.exists() and p2.exists() and p3.exists()


def test_save_sheet_overwrite_clobbers(tmp_path):
    target = tmp_path / "sheet.png"
    s_over = _settings(format="png", overwrite=True)

    save_sheet(_tiny_image(color=(0, 255, 0)), target, s_over)
    written = save_sheet(_tiny_image(color=(0, 0, 255)), target, s_over)

    assert written == target
    with Image.open(written) as img:
        assert img.convert("RGB").getpixel((0, 0)) == (0, 0, 255)


def test_save_sheet_jpeg_flattens_rgba(tmp_path):
    target = tmp_path / "sheet.jpg"
    s = _settings(format="jpeg", overwrite=True, quality=85, bg_contact="white")

    rgba = Image.new("RGBA", (8, 8), (255, 0, 0, 128))
    written = save_sheet(rgba, target, s)

    assert written.exists()
    with Image.open(written) as reloaded:
        assert reloaded.mode == "RGB"


def test_save_sheet_jpeg_quality_param_accepted(tmp_path):
    target = tmp_path / "sheet.jpg"
    s = _settings(format="jpeg", overwrite=True, quality=50)

    written = save_sheet(_tiny_image(), target, s)
    assert written.exists()
    with Image.open(written) as reloaded:
        assert reloaded.mode in ("RGB", "L")
