"""Output path templating and image saving (safe-rename, JPEG flatten)."""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from .config import Settings
from .errors import OutputError, UsageError

_TOKEN_RE = re.compile(r"\{(\w+)\}")
_VALID_TOKENS = {"stem", "name", "dir", "ext"}


def resolve_output_path(input_path: Path, s: Settings) -> Path:
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
    return result if result.is_absolute() else Path.cwd() / result


def _safe_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    parent = path.parent
    n = 1
    while True:
        candidate = parent / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def save_sheet(img: Image.Image, path: Path, s: Settings) -> Path:
    target = path if s.overwrite else _safe_path(path)
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
            img_to_save.save(target, quality=s.quality)
        else:
            img.save(target)
    except OSError as e:
        raise OutputError(f"failed to write {target}: {e}") from None
    return target
