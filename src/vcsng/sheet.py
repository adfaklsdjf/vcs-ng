"""Assemble the final contact sheet: heading + title + thumbnail grid + footer."""

from __future__ import annotations

import getpass
import math
from fractions import Fraction
from typing import TYPE_CHECKING

from PIL import Image

from . import PROGRAM_SIGNATURE
from .config import Settings
from .fonts import load_font
from .render import (
    apply_timestamp,
    drop_shadow,
    heading_block,
    placeholder_tile,
    scale_pts,
    text_block,
)
from .values import Percent, pretty_duration, pretty_size, pretty_stamp

if TYPE_CHECKING:
    from .probe import VideoInfo


def _resolve_thumb_h(
    s: Settings, frames: list[tuple[float, Image.Image | None]], info
) -> int:
    if isinstance(s.height, Percent):
        base = info.height
        for _, im in frames:
            if im is not None:
                base = im.height
                break
        return max(int(round(s.height.resolve(base))), 1)
    return max(int(s.height), 1)


def _heading(info, s: Settings, width: int) -> Image.Image:
    left = [
        f"Filename: {info.path.name}",
        f"File size: {pretty_size(info.file_size)}",
        f"Length: {pretty_duration(info.duration)}",
    ]
    fps = f"{info.fps:.2f}" if info.fps else "unknown"
    fmt = f"{info.vcodec} / {info.acodec or 'none'}"
    ch = info.audio_channels
    if ch == 1:
        fmt += " (mono)"
    elif ch not in (None, 1, 2):
        fmt += f" ({ch}ch)"
    right = [
        f"Dimensions: {info.width}x{info.height}",
        f"Format: {fmt}",
        f"FPS: {fps}",
    ]
    font = load_font(s.font_heading, s.pts_heading)
    return heading_block(left, right, font, s.fg_heading, s.bg_heading, width, border=9)


def _footer(s: Settings, width: int) -> Image.Image | None:
    """Build the footer, or None when there's nothing left to show."""
    lines: list[str] = []
    if not s.anonymous:
        who = s.username or getpass.getuser()
        lines.append(f"{s.signature} {who}")
        if s.credit:
            lines.append(f"with {PROGRAM_SIGNATURE}")
    elif s.credit:
        lines.append(f"Created with {PROGRAM_SIGNATURE}")
    if not lines:
        return None
    font = load_font(s.font_sign, s.pts_sign)
    return text_block(
        lines, font, s.fg_sign, s.bg_sign, width, align="center", pad=(0, 4, 0, 4)
    )


def _widen(img: Image.Image, width: int, bg: tuple[int, int, int, int]) -> Image.Image:
    """Return img centered on a bg-filled canvas of the given width."""
    if img.width == width:
        return img
    canvas = Image.new("RGBA", (width, img.height), bg)
    canvas.alpha_composite(img, ((width - img.width) // 2, 0))
    return canvas


def build_sheet(
    info,
    frames: list[tuple[float, Image.Image | None]],
    s: Settings,
    aspect: Fraction,
) -> Image.Image:
    from .render import parse_color

    thumb_h = _resolve_thumb_h(s, frames, info)
    thumb_w = max(int(round(thumb_h * aspect)), 1)
    bg_contact = parse_color(s.bg_contact)

    ts_font = load_font(s.font_tstamps, scale_pts(s.pts_tstamps, thumb_h))

    tiles: list[Image.Image] = []
    for stamp, frame in frames:
        if frame is None:
            tile = placeholder_tile((thumb_w, thumb_h))
        else:
            tile = frame.convert("RGBA").resize((thumb_w, thumb_h), Image.LANCZOS)
        if s.timestamps:
            apply_timestamp(
                tile, pretty_stamp(stamp), ts_font, s.fg_tstamps, s.bg_tstamps
            )
        if s.shadows:
            tile = drop_shadow(tile)
        tiles.append(tile)

    n = len(tiles)
    cols = max(min(s.columns, n), 1)
    rows = math.ceil(n / cols) if n else 0
    cell_w = (tiles[0].width if tiles else thumb_w) + 2 * s.padding
    cell_h = (tiles[0].height if tiles else thumb_h) + 2 * s.padding
    grid_w = cell_w * cols
    grid_h = cell_h * rows
    grid = Image.new("RGBA", (max(grid_w, 1), max(grid_h, 1)), bg_contact)
    for idx, tile in enumerate(tiles):
        r, c = divmod(idx, cols)
        x = c * cell_w + s.padding
        y = r * cell_h + s.padding
        grid.alpha_composite(tile, (x, y))

    heading = _heading(info, s, grid_w)
    sheet_w = max(grid_w, heading.width)
    heading = _heading(info, s, sheet_w)  # re-render at final width

    parts: list[Image.Image] = [_widen(heading, sheet_w, parse_color(s.bg_heading))]
    if s.title:
        tfont = load_font(s.font_title, s.pts_title)
        title = text_block(
            [s.title], tfont, s.fg_title, s.bg_title, sheet_w,
            align="center", pad=(0, 6, 0, 6),
        )
        parts.append(_widen(title, sheet_w, parse_color(s.bg_title)))
    parts.append(_widen(grid, sheet_w, bg_contact))
    footer = _footer(s, sheet_w)
    if footer is not None:
        parts.append(_widen(footer, sheet_w, parse_color(s.bg_sign)))

    total_h = sum(p.height for p in parts)
    sheet = Image.new("RGBA", (sheet_w, max(total_h, 1)), bg_contact)
    y = 0
    for p in parts:
        sheet.alpha_composite(p, (0, y))
        y += p.height
    return sheet
