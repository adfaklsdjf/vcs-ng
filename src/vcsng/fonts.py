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


_BUNDLED_NAMES = {"", "dejavusans", "dejavu sans", "dejavu-sans"}


@lru_cache(maxsize=None)
def _resolve(spec: str) -> str:
    """Map a font spec (path or family name) to a font file path.

    DejaVu Sans is bundled with the package, so asking for it -- by name, or by a
    path to a DejaVuSans.ttf that doesn't exist on this machine (e.g. a config
    shared between macOS and Linux) -- uses the bundled copy without searching
    the system font directories. Cached so each spec is resolved/logged once.
    """
    if spec and Path(spec).expanduser().is_file():
        return str(Path(spec).expanduser())
    if Path(spec).stem.lower() in _BUNDLED_NAMES:
        if spec.lower() not in _BUNDLED_NAMES:
            log.debug("font %r not found; using bundled DejaVuSans", spec)
        return _bundled_path()
    found = _find_family(spec)
    if found:
        return found
    log.warning("font %r not found; falling back to bundled DejaVuSans", spec)
    return _bundled_path()


@lru_cache(maxsize=None)
def _load_cached(path: str, pts: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, pts)


def load_font(spec: str, pts: int) -> ImageFont.FreeTypeFont:
    """Load a font by file path or family name; never raises for missing font."""
    return _load_cached(_resolve(spec), pts)
