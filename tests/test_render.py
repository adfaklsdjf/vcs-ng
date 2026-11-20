"""Structural tests for fonts, render primitives, and sheet assembly."""

from __future__ import annotations

import types
from fractions import Fraction

import pytest
from PIL import Image

from vcsng.config import Settings
from vcsng.errors import UsageError
from vcsng.fonts import _bundled_path, load_font
from vcsng.render import (
    apply_timestamp,
    drop_shadow,
    heading_block,
    parse_color,
    placeholder_tile,
    scale_pts,
    text_block,
)
from vcsng.sheet import build_sheet


# --- parse_color ---------------------------------------------------------

def test_parse_color_name():
    assert parse_color("black") == (0, 0, 0, 255)


def test_parse_color_hex6():
    assert parse_color("#afcd7a") == (0xAF, 0xCD, 0x7A, 255)


def test_parse_color_hex8():
    assert parse_color("#000000aa") == (0, 0, 0, 170)


def test_parse_color_named2():
    r = parse_color("slategray")
    assert len(r) == 4 and r[3] == 255


def test_parse_color_invalid():
    with pytest.raises(UsageError):
        parse_color("not-a-color")


# --- scale_pts -----------------------------------------------------------

def test_scale_pts_thresholds():
    assert scale_pts(36, 330) == 24
    assert scale_pts(36, 150) == 12
    assert scale_pts(14, 500) == 14


def test_scale_pts_floor():
    assert scale_pts(9, 150) == 7  # 9//3=3 -> floored to 7


# --- drop_shadow ---------------------------------------------------------

def test_drop_shadow_dims():
    img = Image.new("RGBA", (40, 30), (255, 0, 0, 255))
    out = drop_shadow(img, radius=2, offset=(4, 4), opacity=0.5)
    assert out.width == 40 + 4 + 2 * 2
    assert out.height == 30 + 4 + 2 * 2


# --- apply_timestamp -----------------------------------------------------

def test_apply_timestamp_changes_pixels():
    thumb = Image.new("RGBA", (200, 120), (10, 20, 30, 255))
    before = thumb.copy()
    font = load_font("DejaVuSans", 14)
    apply_timestamp(thumb, "00:20.00", font, "white", "black")
    # bottom-right region changed
    assert thumb.getpixel((190, 110)) != before.getpixel((190, 110))
    # top-left untouched
    assert thumb.getpixel((5, 5)) == (10, 20, 30, 255)


def test_apply_timestamp_alpha_bg_translucent():
    thumb = Image.new("RGBA", (200, 120), (200, 50, 50, 255))
    font = load_font("DejaVuSans", 14)
    apply_timestamp(thumb, "00:20.00", font, "#00000080", "#00000080")
    # sample a pixel in the box area away from glyphs: underlying red still bleeds
    px = thumb.getpixel((198, 118))
    assert px[0] > 0  # some red channel survives the translucent black box


def test_apply_timestamp_text_vertically_centered():
    # Regression: text must sit centered in the box (equal padding top/bottom),
    # not jammed against the top edge as it was before.
    thumb = Image.new("RGBA", (300, 200), (0, 0, 0, 255))
    font = load_font("DejaVuSans", 24)
    # green box so it's distinguishable from both the black bg and white ink
    apply_timestamp(thumb, "00:40.00", font, "white", "#00ff00")
    px = thumb.load()

    def is_box(p):
        return p[1] > 100 and p[0] < 100  # greenish

    def is_ink(p):
        return p[0] > 200 and p[1] > 200 and p[2] > 200  # white

    cols = range(180, 300)
    box_rows = [y for y in range(200) if any(is_box(px[x, y]) for x in cols)]
    ink_rows = [y for y in range(200) if any(is_ink(px[x, y]) for x in cols)]
    assert box_rows and ink_rows
    pad_top = min(ink_rows) - min(box_rows)
    pad_bottom = max(box_rows) - max(ink_rows)
    # symmetric within a pixel or two (glyph metrics aren't perfectly symmetric)
    assert abs(pad_top - pad_bottom) <= 2, (pad_top, pad_bottom)


# --- text_block / heading_block ------------------------------------------

def test_text_block_dims():
    font = load_font("DejaVuSans", 14)
    img = text_block(["hello", "world"], font, "black", "white", 300)
    assert img.width == 300
    assert img.height > 0


def test_text_block_center_and_right():
    font = load_font("DejaVuSans", 14)
    for align in ("left", "center", "right"):
        img = text_block(["x"], font, "black", "white", 100, align=align)
        assert img.width == 100


def test_heading_block_dims():
    font = load_font("DejaVuSans", 14)
    img = heading_block(["a", "b"], ["c", "d"], font, "black", "#afcd7a", 400)
    assert img.width == 400
    assert img.height > 18


def test_heading_block_expands_for_wide_text():
    font = load_font("DejaVuSans", 14)
    wide = "x" * 400
    img = heading_block([wide], [wide], font, "black", "#afcd7a", 100)
    assert img.width > 100


# --- load_font -----------------------------------------------------------

def test_load_font_by_path():
    f = load_font(_bundled_path(), 12)
    assert f is not None


def test_load_font_garbage_falls_back():
    f = load_font("no-such-font-xyz", 12)
    assert f is not None  # bundled fallback, no raise


def test_load_font_lru_cache():
    a = load_font("DejaVuSans", 20)
    b = load_font("DejaVuSans", 20)
    assert a is b


# --- placeholder_tile ----------------------------------------------------

def test_placeholder_tile():
    t = placeholder_tile((160, 90))
    assert t.size == (160, 90)
    assert t.getpixel((0, 0)) == (0x33, 0x33, 0x33, 255)


# --- build_sheet ---------------------------------------------------------

def _info():
    from pathlib import Path

    return types.SimpleNamespace(
        path=Path("/videos/sample movie.mkv"),
        duration=3903.0,
        width=1280,
        height=720,
        sar=None,
        dar=None,
        fps=23.976,
        vcodec="h264",
        acodec="aac",
        audio_channels=2,
        rotation=0,
        file_size=734003200,
    )


def _frames(n=5, with_none=False):
    colors = [(200, 50, 50), (50, 200, 50), (50, 50, 200), (200, 200, 50), (50, 200, 200)]
    out = []
    for i in range(n):
        if with_none and i == 2:
            out.append((float(i * 60), None))
        else:
            out.append((float(i * 60), Image.new("RGB", (320, 180), colors[i % len(colors)])))
    return out


def test_build_sheet_basic():
    s = Settings(columns=3, height=90, timestamps=True, shadows=True)
    sheet = build_sheet(_info(), _frames(5), s, Fraction(16, 9))
    assert isinstance(sheet, Image.Image)
    assert sheet.mode == "RGBA"
    # grid region not uniform (thumbnails pasted)
    colors = {sheet.getpixel((x, sheet.height // 2)) for x in range(0, sheet.width, 20)}
    assert len(colors) > 1


def test_build_sheet_width_is_max_of_grid_and_heading():
    s = Settings(columns=3, height=90, timestamps=True, shadows=True)
    sheet = build_sheet(_info(), _frames(5), s, Fraction(16, 9))
    # heading with a long filename can force width wider than grid, or grid wins.
    # Either way width must be >= a single cell.
    assert sheet.width >= 90 * 16 // 9


def test_build_sheet_placeholder_path():
    s = Settings(columns=3, height=90, timestamps=True, shadows=False)
    sheet = build_sheet(_info(), _frames(5, with_none=True), s, Fraction(16, 9))
    assert isinstance(sheet, Image.Image)


def test_build_sheet_anonymous_vs_named_height():
    frames = _frames(5)
    named = build_sheet(_info(), frames, Settings(columns=3, height=90, anonymous=False), Fraction(16, 9))
    anon = build_sheet(_info(), frames, Settings(columns=3, height=90, anonymous=True), Fraction(16, 9))
    # named footer has 2 lines, anonymous 1 -> different height
    assert named.height != anon.height


def test_build_sheet_credit_toggle():
    frames = _frames(5)
    base = dict(columns=3, height=90)
    # anonymous + no credit -> no footer at all; strictly shorter than with credit
    anon_credit = build_sheet(_info(), frames, Settings(**base, anonymous=True, credit=True), Fraction(16, 9))
    anon_nocredit = build_sheet(_info(), frames, Settings(**base, anonymous=True, credit=False), Fraction(16, 9))
    assert anon_nocredit.height < anon_credit.height
    # named + no credit -> single footer line, shorter than the two-line credited footer
    named_credit = build_sheet(_info(), frames, Settings(**base, anonymous=False, credit=True), Fraction(16, 9))
    named_nocredit = build_sheet(_info(), frames, Settings(**base, anonymous=False, credit=False), Fraction(16, 9))
    assert named_nocredit.height < named_credit.height


# --- font resolution -----------------------------------------------------

def test_dejavu_name_uses_bundled_without_search(monkeypatch):
    from vcsng import fonts

    fonts._resolve.cache_clear()
    monkeypatch.setattr(fonts, "_find_family", lambda spec: pytest.fail("searched"))
    assert fonts._resolve("DejaVuSans") == _bundled_path()


def test_missing_dejavu_path_falls_back_quietly(caplog):
    from vcsng import fonts

    fonts._resolve.cache_clear()
    with caplog.at_level("DEBUG", logger="vcsng"):
        assert fonts._resolve("/nonexistent/DejaVuSans.ttf") == _bundled_path()
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_missing_other_font_warns_once(caplog, monkeypatch):
    from vcsng import fonts

    fonts._resolve.cache_clear()
    monkeypatch.setattr(fonts, "_find_family", lambda spec: None)
    with caplog.at_level("WARNING", logger="vcsng"):
        fonts._resolve("NoSuchFont")
        fonts._resolve("NoSuchFont")
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1


@pytest.mark.parametrize("pad_x,pad_y", [(6, 6), (0, 10)])
def test_apply_timestamp_box_is_text_plus_padding(pad_x, pad_y):
    font = load_font("DejaVuSans", 20)
    thumb = Image.new("RGBA", (300, 200), (255, 255, 255, 255))
    apply_timestamp(thumb, "01:23.45", font, "black", "black", pad_x, pad_y)
    l, t, r, b = thumb.convert("L").point(lambda v: 255 - v).getbbox()
    bb = font.getbbox("01:23.45")
    assert (r - l, b - t) == (bb[2] - bb[0] + 2 * pad_x, bb[3] - bb[1] + 2 * pad_y)
    assert (300 - r, 200 - b) == (5, 5)  # margin from bottom-right


def test_tstamp_padding_from_config(tmp_path):
    from vcsng.config import build_settings

    cfg = tmp_path / "c.toml"
    cfg.write_text("[style]\ntstamp_pad_x = 3\ntstamp_pad_y = 8\n")
    s = build_settings({}, config_path=cfg)
    assert (s.tstamp_pad_x, s.tstamp_pad_y) == (3, 8)
