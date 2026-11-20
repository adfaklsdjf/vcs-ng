"""Primitive image-composition helpers: text, headings, timestamps, shadows."""

from __future__ import annotations

from PIL import Image, ImageColor, ImageDraw, ImageFont

from .errors import UsageError
from .fonts import load_font


def parse_color(s: str) -> tuple[int, int, int, int]:
    """Parse a color name / #rgb / #rrggbb / #rrggbbaa into an RGBA 4-tuple."""
    try:
        rgb = ImageColor.getrgb(s)
    except ValueError:
        raise UsageError(f"invalid color: {s!r}") from None
    if len(rgb) == 4:
        return rgb
    return (rgb[0], rgb[1], rgb[2], 255)


def _line_metrics(font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    """(ascent+descent height, descent) for consistent line spacing."""
    ascent, descent = font.getmetrics()
    return ascent + descent, descent


def text_block(
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    fg: str,
    bg: str,
    width: int,
    *,
    align: str = "left",
    pad: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> Image.Image:
    """Render lines onto a bg-filled RGBA image of the given width."""
    pl, pt, pr, pb = pad
    line_h, _ = _line_metrics(font)
    n = max(len(lines), 0)
    inner_h = line_h * n
    height = inner_h + pt + pb
    if width <= 0:
        # width from longest line
        tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        maxw = 0
        for ln in lines:
            bb = tmp.textbbox((0, 0), ln, font=font)
            maxw = max(maxw, bb[2] - bb[0])
        width = maxw + pl + pr
    width = max(width, 1)
    height = max(height, 1)
    img = Image.new("RGBA", (width, height), parse_color(bg))
    draw = ImageDraw.Draw(img)
    fgc = parse_color(fg)
    for i, ln in enumerate(lines):
        y = pt + i * line_h
        if align == "left":
            x, anchor = pl, "la"
        elif align == "right":
            x, anchor = width - pr, "ra"
        else:  # center
            x, anchor = width // 2, "ma"
        draw.text((x, y), ln, font=font, fill=fgc, anchor=anchor)
    return img


def heading_block(
    left_lines: list[str],
    right_lines: list[str],
    font: ImageFont.FreeTypeFont,
    fg: str,
    bg: str,
    width: int,
    *,
    border: int = 9,
) -> Image.Image:
    """Two-column metadata header wrapped in a `border`-px bg margin."""
    line_h, _ = _line_metrics(font)
    n = max(len(left_lines), len(right_lines))
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def widest(lines: list[str]) -> int:
        w = 0
        for ln in lines:
            bb = tmp.textbbox((0, 0), ln, font=font)
            w = max(w, bb[2] - bb[0])
        return w

    gap = 20  # min space between columns
    natural = border * 2 + widest(left_lines) + gap + widest(right_lines)
    width = max(width, natural)
    inner_w = width - 2 * border
    height = border * 2 + line_h * n
    img = Image.new("RGBA", (width, max(height, 1)), parse_color(bg))
    draw = ImageDraw.Draw(img)
    fgc = parse_color(fg)
    for i, ln in enumerate(left_lines):
        draw.text((border, border + i * line_h), ln, font=font, fill=fgc, anchor="la")
    for i, ln in enumerate(right_lines):
        draw.text(
            (border + inner_w, border + i * line_h),
            ln,
            font=font,
            fill=fgc,
            anchor="ra",
        )
    return img


def apply_timestamp(
    thumb: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    fg: str,
    bg: str,
    pad_x: int = 10,
    pad_y: int = 10,
) -> None:
    """Draw text in a bg box (pad_x/pad_y px of padding around the glyphs)
    anchored 5px from the bottom-right; mutates thumb."""
    label = text
    tmp = ImageDraw.Draw(thumb)
    bb = tmp.textbbox((0, 0), label, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    box_w, box_h = tw + pad_x * 2, th + pad_y * 2
    margin = 5
    x0 = thumb.width - box_w - margin
    y0 = thumb.height - box_h - margin
    # composite bg box (may be translucent) rather than overwriting pixels
    box = Image.new("RGBA", (box_w, box_h), parse_color(bg))
    thumb.alpha_composite(box, (max(x0, 0), max(y0, 0)))
    draw = ImageDraw.Draw(thumb)
    # center the glyph bbox within the box; subtract bb offsets so the drawn
    # ink lands exactly pad_x/pad_y from the box's top-left corner
    draw.text(
        (x0 + pad_x - bb[0], y0 + pad_y - bb[1]),
        label,
        font=font,
        fill=parse_color(fg),
    )


def scale_pts(pts: int, thumb_height: int) -> int:
    """Original vcs point-scaling rule, floored at 7."""
    if thumb_height < 200:
        v = pts // 3
    elif thumb_height < 400:
        v = pts * 2 // 3
    else:
        v = pts
    return max(int(v), 7)


def drop_shadow(
    img: Image.Image,
    *,
    radius: int = 2,
    offset: tuple[int, int] = (4, 4),
    opacity: float = 0.5,
) -> Image.Image:
    """Reproduce ImageMagick `-shadow 50x2+4+4`. Returns a new RGBA image."""
    from PIL import ImageFilter

    img = img.convert("RGBA")
    ox, oy = offset
    margin = radius  # symmetric growth = radius on every side, plus offset
    out_w = img.width + abs(ox) + 2 * margin
    out_h = img.height + abs(oy) + 2 * margin
    canvas = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))

    # black silhouette from alpha, scaled by opacity
    alpha = img.getchannel("A").point(lambda a: int(a * opacity))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow.putalpha(alpha)
    shadow_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    shadow_layer.paste(shadow, (margin + ox, margin + oy))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius))

    canvas = Image.alpha_composite(canvas, shadow_layer)
    canvas.alpha_composite(img, (margin, margin))
    return canvas


def placeholder_tile(size: tuple[int, int], text: str = "capture failed") -> Image.Image:
    """#333 tile with centered white text."""
    w, h = size
    img = Image.new("RGBA", (max(w, 1), max(h, 1)), (0x33, 0x33, 0x33, 255))
    pts = max(min(h // 8, 24), 7)
    font = load_font("DejaVuSans", pts)
    draw = ImageDraw.Draw(img)
    draw.text((w // 2, h // 2), text, font=font, fill=(255, 255, 255, 255), anchor="mm")
    return img
