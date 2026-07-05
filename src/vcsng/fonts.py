"""Font resolution with an always-available bundled fallback."""

from __future__ import annotations

import logging
from functools import lru_cache
from importlib import resources
from pathlib import Path

from PIL import ImageFont

log = logging.getLogger("vcsng")

_FONT_DIRS = (
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "~/.local/share/fonts",
    "/Library/Fonts",
    "/System/Library/Fonts",
    "~/Library/Fonts",
)


def _bundled_path() -> str:
    ref = resources.files("vcsng.data.fonts") / "DejaVuSans.ttf"
    with resources.as_file(ref) as p:
        return str(p)


def _find_family(spec: str) -> str | None:
    """Case-insensitive recursive search for {spec}.ttf/.otf under font dirs."""
    variants = {spec.lower(), spec.replace(" ", "").replace("-", "").lower()}
    for d in _FONT_DIRS:
        base = Path(d).expanduser()
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix.lower() not in (".ttf", ".otf"):
                continue
            if path.stem.lower() in variants:
                return str(path)
    return None


def _resolve(spec: str) -> str:
    if spec and Path(spec).is_file():
        return spec
    found = _find_family(spec) if spec else None
    if found:
        return found
    if spec and spec.lower() not in ("dejavusans", ""):
        log.warning("font %r not found; falling back to bundled DejaVuSans", spec)
    return _bundled_path()


@lru_cache(maxsize=None)
def _load_cached(path: str, pts: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, pts)


def load_font(spec: str, pts: int) -> ImageFont.FreeTypeFont:
    """Load a font by file path or family name; never raises for missing font."""
    return _load_cached(_resolve(spec), pts)
