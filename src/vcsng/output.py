"""Output path templating and image saving (safe-rename, JPEG flatten)."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from PIL import Image

from .config import Settings
from .console import FileName
from .errors import OutputError, UsageError

log = logging.getLogger("vcsng")

JPEG_MAX_SIDE = 65500  # libjpeg's limit; Pillow fails with "broken data stream"

_TOKEN_RE = re.compile(r"\{(\w+)\}")
_VALID_TOKENS = {"stem", "name", "dir", "ext"}


def check_sheet_size(size: tuple[int, int], s: Settings) -> None:
    """Fail up front, before any capturing, if the format can't hold a sheet
    this size (e.g. a very long video, or one whose length is misreported)."""
    w, h = size
    if s.format == "jpeg" and max(w, h) > JPEG_MAX_SIDE:
        raise OutputError(
            "sheet would be %dx%dpx, over JPEG's %dpx limit; try fewer captures "
            "(-n/-i), a smaller --height, more --columns, or -f png",
            w, h, JPEG_MAX_SIDE,
        )


def resolve_output_path(input_path: Path, s: Settings, base_dir: Path | None = None) -> Path:
    """Expand the output template. Relative results are resolved against
    base_dir (directory scans pass the video's own directory) or else the CWD."""
    template = s.output or "{stem}.{ext}"
    ext = "jpg" if s.format == "jpeg" else s.format
    stem = input_path.stem + s.suffix

    tokens = {
        "stem": stem,
        "name": stem + input_path.suffix,
        "dir": str(input_path.parent),
        "ext": ext,
    }

    for match in _TOKEN_RE.finditer(template):
        name = match.group(1)
        if name not in _VALID_TOKENS:
            raise UsageError(f"unknown output template token: {{{name}}}")

    formatted = _TOKEN_RE.sub(lambda m: tokens[m.group(1)], template)
    result = Path(formatted)
    return result if result.is_absolute() else (base_dir or Path.cwd()) / result


def _old_path(path: Path) -> Path:
    """First free name for retiring an existing sheet: NAME-old.EXT, then
    NAME-old1.EXT, NAME-old2.EXT, ..."""
    n = 0
    while True:
        candidate = path.with_name(f"{path.stem}-old{n or ''}{path.suffix}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        n += 1


def save_sheet(img: Image.Image, target: Path, s: Settings) -> Path:
    """Write via a hidden temp file + rename, so an interrupted run never leaves
    a half-written sheet in place of a good one.

    Whatever already exists at target is renamed to NAME-old.EXT (see _old_path)
    once the new sheet is fully written, unless s.overwrite says to clobber it."""
    if target.is_dir():
        raise OutputError("output path is a directory: %s", target)
    tmp = target.with_name(f".{target.name}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if s.format == "jpeg":
            from .render import parse_color

            if img.mode != "RGB":
                bg_rgba = parse_color(s.bg_contact)
                flattened = Image.new("RGB", img.size, bg_rgba[:3])
                if img.mode == "RGBA":
                    flattened.paste(img, mask=img.split()[3])
                else:
                    flattened.paste(img.convert("RGBA"))
                img_to_save = flattened
            else:
                img_to_save = img
            img_to_save.save(tmp, format="JPEG", quality=s.quality)
        else:
            img.save(tmp, format="PNG")
        if not s.overwrite and (target.exists() or target.is_symlink()):
            old = _old_path(target)
            target.rename(old)
            log.info("moved %s -> %s", target, FileName(old.name))
        os.replace(tmp, target)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise OutputError("failed to write %s", target, detail=str(e)) from None
    return target
