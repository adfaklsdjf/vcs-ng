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
    parse_color,
    placeholder_tile,
    scale_pts,
    shadow_growth,
    text_block,
)
from .values import Percent, pretty_duration, pretty_size, pretty_stamp

if TYPE_CHECKING:
    from .probe import VideoInfo

# Pillow's decompression-bomb guard is for decoding untrusted files; it also
# fires on crop(), which alpha_composite() uses internally, so it trips on our
# own canvases once a sheet has enough captures (e.g. ~900 frames at 4 columns).
Image.MAX_IMAGE_PIXELS = None


# --- geometry -------------------------------------------------------------
# Shared by build_sheet and predict_sheet_size so the prediction can't drift
# from what actually gets rendered.

def thumb_size(s: Settings, source_h: int, aspect: Fraction) -> tuple[int, int]:
    """Thumbnail (w, h) before shadows; source_h is the (rotation-corrected)
    video height from the probe."""
    if isinstance(s.height, Percent):
        h = max(int(round(s.height.resolve(source_h))), 1)
    else:
        h = max(int(s.height), 1)
    return max(int(round(h * aspect)), 1), h


def _grid(n: int, thumb: tuple[int, int], s: Settings) -> tuple[int, int, int, int]:
    """(cols, rows, cell_w, cell_h) for n tiles of the given thumbnail size."""
    tile_w, tile_h = thumb
    if s.shadows:
        grow_w, grow_h = shadow_growth()
        tile_w, tile_h = tile_w + grow_w, tile_h + grow_h
    cols = max(min(s.columns, n), 1)
    rows = math.ceil(n / cols) if n else 0
    return cols, rows, tile_w + 2 * s.padding, tile_h + 2 * s.padding


def predict_sheet_size(info: VideoInfo, n_caps: int, s: Settings) -> tuple[int, int]:
    """(width, height) build_sheet would produce for this video, without
    capturing frames. Renders only the (small) heading, title and footer."""
    from .aspect import resolve_aspect

    aspect = resolve_aspect(info.width, info.height, info.dar, s.aspect)
    cols, rows, cell_w, cell_h = _grid(n_caps, thumb_size(s, info.height, aspect), s)
    sheet_w, above, below = _surround(info, s, cell_w * cols)
    return sheet_w, sum(p.height for p in above + below) + max(cell_h * rows, 1)


def _surround(
    info, s: Settings, grid_w: int
) -> tuple[int, list[Image.Image], list[Image.Image]]:
    """(sheet width, parts above the grid, parts below it), all at sheet width."""
    sheet_w = max(grid_w, _heading(info, s, grid_w).width)
    # re-render the heading at the final width
    above = [_widen(_heading(info, s, sheet_w), sheet_w, parse_color(s.bg_heading))]
    if s.title:
        tfont = load_font(s.font_title, s.pts_title)
        title = text_block(
            [s.title], tfont, s.fg_title, s.bg_title, sheet_w,
            align="center", pad=(0, 6, 0, 6),
        )
        above.append(_widen(title, sheet_w, parse_color(s.bg_title)))
    footer = _footer(s, sheet_w)
    below = [_widen(footer, sheet_w, parse_color(s.bg_sign))] if footer is not None else []
    return sheet_w, above, below


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
    """Frames may arrive already shrunk to thumb_size (capture_frames does
    this to keep memory down); any other size is resized here."""
    thumb_w, thumb_h = thumb_size(s, info.height, aspect)
    bg_contact = parse_color(s.bg_contact)

    ts_font = load_font(s.font_tstamps, scale_pts(s.pts_tstamps, thumb_h))

    tiles: list[Image.Image] = []
    for stamp, frame in frames:
        if frame is None:
            tile = placeholder_tile((thumb_w, thumb_h))
        else:
            tile = frame.convert("RGBA")
            if tile.size != (thumb_w, thumb_h):
                tile = tile.resize((thumb_w, thumb_h), Image.LANCZOS)
        if s.timestamps:
            apply_timestamp(
                tile, pretty_stamp(stamp), ts_font, s.fg_tstamps, s.bg_tstamps,
                s.tstamp_pad_x, s.tstamp_pad_y,
            )
        if s.shadows:
            tile = drop_shadow(tile)
        tiles.append(tile)

    cols, rows, cell_w, cell_h = _grid(len(tiles), (thumb_w, thumb_h), s)
    grid_w = cell_w * cols
    grid_h = cell_h * rows
    grid = Image.new("RGBA", (max(grid_w, 1), max(grid_h, 1)), bg_contact)
    for idx, tile in enumerate(tiles):
        r, c = divmod(idx, cols)
        x = c * cell_w + s.padding
        y = r * cell_h + s.padding
        grid.alpha_composite(tile, (x, y))

    sheet_w, above, below = _surround(info, s, grid_w)
    parts = [*above, _widen(grid, sheet_w, bg_contact), *below]

    total_h = sum(p.height for p in parts)
    sheet = Image.new("RGBA", (sheet_w, max(total_h, 1)), bg_contact)
    y = 0
    for p in parts:
        sheet.alpha_composite(p, (0, y))
        y += p.height
    return sheet
