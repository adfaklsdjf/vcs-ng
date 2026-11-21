"""Recursive directory scanning and existing-output inspection.

Used when a directory is given on the command line (or -r): every video under
it gets a contact sheet next to it, unless an acceptable one already exists.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterator
from enum import Enum
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .errors import OutputError

log = logging.getLogger("vcsng")

# "sample" as a whole word: matches "sample", "movie-sample", "Sample.1080p",
# but not "samples_of_jazz" or "resampled".
_SAMPLE_RE = re.compile(r"(?<![a-z0-9])sample(?![a-z0-9])", re.IGNORECASE)
_SAMPLE_DIRS = {"sample", "samples"}


def iter_videos(root: Path, extensions: tuple[str, ...]) -> Iterator[Path]:
    """Yield video files under root in sorted order.

    Skips hidden files/dirs, symlinks (files and dirs), sample dirs, and files
    whose name contains the word "sample".
    """
    exts = {"." + e for e in extensions}

    def on_error(err: OSError) -> None:
        log.warning("cannot read %s: %s", err.filename, err.strerror)

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
        base = Path(dirpath)
        keep = []
        for d in sorted(dirnames):
            if d.startswith("."):
                continue
            if d.lower() in _SAMPLE_DIRS:
                log.debug("skipping sample dir %s", base / d)
                continue
            if (base / d).is_symlink():
                log.debug("skipping symlinked dir %s", base / d)
                continue
            keep.append(d)
        dirnames[:] = keep  # prune in place so os.walk doesn't descend

        for name in sorted(filenames):
            path = base / name
            if name.startswith(".") or path.suffix.lower() not in exts:
                continue
            if path.is_symlink():
                log.debug("skipping symlink %s", path)
                continue
            if _SAMPLE_RE.search(path.stem):
                log.debug("skipping sample %s", path)
                continue
            yield path


class Existing(Enum):
    MISSING = "missing"
    OK = "ok"  # valid image of the expected format (and >= min_width, if set)
    UNDERSIZED = "undersized"  # valid image of the expected format, < min_width
    BAD = "bad"  # unreadable, truncated, wrong format, or not an image at all


_PIL_FORMAT = {"jpeg": "JPEG", "png": "PNG"}


def _looks_complete(path: Path, pil_format: str) -> bool:
    """Cheap truncation check: the file ends with the format's end marker."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - 64))
        tail = fh.read()
    if pil_format == "JPEG":
        return tail.rstrip(b"\x00").endswith(b"\xff\xd9")
    if pil_format == "PNG":
        return tail.endswith(b"IEND\xaeB`\x82")
    return True


def check_existing(
    path: Path, fmt: str, min_width: int | None
) -> tuple[Existing, int | None]:
    """Classify whatever is at an output path. Returns (status, width).

    Width only matters when min_width is set; otherwise any valid image is OK."""
    if not path.exists() and not path.is_symlink():
        return Existing.MISSING, None
    if path.is_dir():
        raise OutputError(f"output path is a directory: {path}")
    if not path.is_file():
        return Existing.BAD, None
    expected = _PIL_FORMAT[fmt]
    try:
        with Image.open(path) as im:
            actual, width = im.format, im.width
    except (UnidentifiedImageError, OSError):
        return Existing.BAD, None
    if actual != expected or not _looks_complete(path, expected):
        return Existing.BAD, width
    if min_width is not None and width < min_width:
        return Existing.UNDERSIZED, width
    return Existing.OK, width


def set_aside(path: Path) -> Path:
    """Rename a file we won't overwrite to <name>.bad (or .bad-N); return new path."""
    candidate = path.with_name(path.name + ".bad")
    n = 1
    while candidate.exists() or candidate.is_symlink():
        candidate = path.with_name(f"{path.name}.bad-{n}")
        n += 1
    path.rename(candidate)
    return candidate
