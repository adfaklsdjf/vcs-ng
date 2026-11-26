"""Frame capture via ffmpeg subprocess calls, in parallel across stamps."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .errors import MissingToolError

log = logging.getLogger("vcsng")

_RETRY_BACKOFFS = (1.0, 5.0)


def _run_ffmpeg(
    path: Path, ts: float, size: tuple[int, int] | None, threads: int
) -> Image.Image | None:
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-threads",
                str(threads),
                "-ss",
                f"{ts:.3f}",
                "-i",
                str(path),
                "-an",
                "-sn",
                "-dn",
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-c:v",
                "png",
                "-",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise MissingToolError("ffmpeg not found; is ffmpeg installed and on PATH?") from None
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    try:
        img = Image.open(BytesIO(proc.stdout))
        img.load()
    except (UnidentifiedImageError, OSError):
        return None
    if size is not None and img.size != size:
        img = img.resize(size, Image.LANCZOS)
    return img.convert("RGBA")


def _grab_one(
    path: Path,
    ts: float,
    size: tuple[int, int] | None,
    threads: int,
    on_capture: Callable[[float], None] | None = None,
) -> Image.Image | None:
    """Grab a single frame at ts, retrying at earlier timestamps on failure.

    This is the future blank-frame-evasion extension point — keep it isolated.
    """
    if on_capture is not None:
        on_capture(ts)
    img = _run_ffmpeg(path, ts, size, threads)
    if img is not None:
        return img
    for backoff in _RETRY_BACKOFFS:
        retry_ts = max(0.0, ts - backoff)
        img = _run_ffmpeg(path, retry_ts, size, threads)
        if img is not None:
            return img
    log.warning("failed to capture frame at %.3fs from %s", ts, path)
    return None


def capture_frames(
    path: Path,
    stamps: list[float],
    workers: int | None = None,
    on_capture: Callable[[float], None] | None = None,
    size: tuple[int, int] | None = None,
) -> list[tuple[float, Image.Image | None]]:
    """Grab a frame per stamp. With size, each frame is shrunk to it as soon as
    it's decoded: holding hundreds of full-resolution (e.g. 4K) frames until the
    sheet is built would take tens of GB."""
    start = time.monotonic()
    cpus = os.cpu_count() or 4
    n_workers = workers or min(len(stamps), cpus) or 1
    # Split the cores between workers rather than letting every ffmpeg start a
    # decoder thread per core: each thread holds its own frame buffers (about
    # 40 MB apiece for 4K), so 16 workers x 16 threads ran into the GBs.
    threads = max(1, cpus // n_workers)

    results: list[Image.Image | None] = [None] * len(stamps)
    if stamps:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            mapped = pool.map(lambda t: _grab_one(path, t, size, threads, on_capture), stamps)
            for i, img in zip(range(len(stamps)), mapped):
                results[i] = img

    elapsed = time.monotonic() - start
    failed = sum(1 for img in results if img is None)
    log.info("captured %d frames (%d failed) in %.1fs", len(stamps), failed, elapsed)
    return list(zip(stamps, results))
