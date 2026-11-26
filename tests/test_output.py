"""Tests for output.py: template expansion, safe-rename, JPEG flatten."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from vcsng.config import Settings
from vcsng.errors import OutputError, UsageError
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


def test_resolve_output_path_suffix_default_template(tmp_path):
    s = _settings(format="jpeg", suffix="-ss")
    result = resolve_output_path(Path("movie.mkv"), s)
    assert result.name == "movie-ss.jpg"


def test_resolve_output_path_suffix_with_name_token(tmp_path):
    s = _settings(format="png", suffix="-ss", output="{name}.contact.{ext}")
    result = resolve_output_path(Path("video.mp4"), s)
    assert result.name == "video-ss.mp4.contact.png"


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


def _color_at(path: Path) -> tuple:
    with Image.open(path) as img:
        return img.convert("RGB").getpixel((0, 0))


def test_save_sheet_renames_existing_to_old(tmp_path):
    target = tmp_path / "sheet-ss.png"
    s = _settings(format="png", overwrite=False)
    red, green, blue = (255, 0, 0), (0, 255, 0), (0, 0, 255)

    for color in (red, green, blue):
        assert save_sheet(_tiny_image(color=color), target, s) == target

    # newest at the intended name; older ones retired as -old, -old1, ...
    assert _color_at(target) == blue
    assert _color_at(tmp_path / "sheet-ss-old.png") == red
    assert _color_at(tmp_path / "sheet-ss-old1.png") == green
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "sheet-ss-old.png", "sheet-ss-old1.png", "sheet-ss.png",
    ]


def test_save_sheet_rejects_directory_target(tmp_path):
    (tmp_path / "sheet.png").mkdir()
    with pytest.raises(OutputError):
        save_sheet(_tiny_image(), tmp_path / "sheet.png", _settings(format="png"))


def test_save_sheet_overwrite_clobbers(tmp_path):
    target = tmp_path / "sheet.png"
    s_over = _settings(format="png", overwrite=True)

    save_sheet(_tiny_image(color=(0, 255, 0)), target, s_over)
    written = save_sheet(_tiny_image(color=(0, 0, 255)), target, s_over)

    assert written == target
    assert _color_at(written) == (0, 0, 255)
    assert list(tmp_path.iterdir()) == [target]


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


def test_check_sheet_size_jpeg_limit():
    from vcsng.errors import OutputError
    from vcsng.output import JPEG_MAX_SIDE, check_sheet_size

    jpeg, png = Settings(format="jpeg"), Settings(format="png")
    check_sheet_size((2000, JPEG_MAX_SIDE), jpeg)
    with pytest.raises(OutputError, match="over JPEG"):
        check_sheet_size((2000, JPEG_MAX_SIDE + 1), jpeg)
    check_sheet_size((2000, JPEG_MAX_SIDE + 1), png)
