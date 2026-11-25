"""Decide up front which contact sheets a run will generate.

Two steps, both before any video is rendered:

1. collect_inputs: expand directory arguments into the videos found under them
   ("found N videos").
2. build_plan: for each video, inspect whatever already exists at its output
   path and decide whether a sheet is needed ("generating M contact sheets").

Execution (in cli) then just walks Plan.jobs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .config import Settings
from .console import FileName
from .errors import OutputError, VcsngError
from .output import resolve_output_path
from .scan import Existing, check_existing, iter_videos

log = logging.getLogger("vcsng")


@dataclass(frozen=True)
class Input:
    video: Path
    scanned: bool  # found by scanning a directory (vs. named on the command line)


class Action(Enum):
    NEW = "new"  # nothing at the output path (or a file named on the CLI)
    REGENERATE = "regenerate"  # replacing a valid sheet (undersized, or --regenerate)
    REPLACE_BAD = "replace_bad"  # output path holds junk; set it aside as NAME.bad first


class Keep(Enum):
    """Why a scanned video's existing sheet is left alone."""

    UP_TO_DATE = "up_to_date"
    CANT_REACH_MIN_WIDTH = "cant_reach_min_width"  # a new sheet would be too narrow too


@dataclass(frozen=True)
class Job:
    video: Path
    out: Path
    action: Action


@dataclass
class Plan:
    jobs: list[Job] = field(default_factory=list)
    up_to_date: int = 0
    too_narrow: int = 0  # undersized, but regenerating wouldn't reach min_width either
    failed: list[tuple[Path, OutputError]] = field(default_factory=list)


def collect_inputs(paths: list[Path], s: Settings, *, recursive: bool) -> list[Input]:
    """Expand directory arguments into scanned videos; files pass through."""
    inputs: list[Input] = []
    for path in paths:
        if not path.is_dir():
            inputs.append(Input(path, scanned=False))
            continue
        if not recursive:
            log.info("%s is a directory; scanning recursively", path)
        found = list(iter_videos(path, s.extensions))
        log.info("%s: found %d video%s", path, len(found), "" if len(found) == 1 else "s")
        inputs.extend(Input(v, scanned=True) for v in found)
    return inputs


def build_plan(inputs: list[Input], s: Settings) -> Plan:
    """Decide which inputs get a sheet. Files named on the command line always
    do; scanned videos only when their existing sheet is missing, not a valid
    image, narrower than s.min_width (if set), or s.regenerate is on.

    Per-video problems (e.g. the output path is a directory) land in
    Plan.failed; UsageError (e.g. a bad -o template) propagates."""
    plan = Plan()
    for inp in inputs:
        try:
            job = _plan_scanned(inp.video, s) if inp.scanned else Job(
                inp.video, resolve_output_path(inp.video, s), Action.NEW
            )
        except OutputError as e:
            plan.failed.append((inp.video, e))
            continue
        if job is Keep.UP_TO_DATE:
            plan.up_to_date += 1
        elif job is Keep.CANT_REACH_MIN_WIDTH:
            plan.too_narrow += 1
        else:
            plan.jobs.append(job)
    return plan


def _plan_scanned(video: Path, s: Settings) -> Job | Keep:
    """Scanned videos get their sheet next to them."""
    out = resolve_output_path(video, s, base_dir=video.parent)
    status, width = check_existing(out, s.format, s.min_width)

    if status is Existing.MISSING:
        return Job(video, out, Action.NEW)
    if status is Existing.BAD:
        log.warning("%s: existing %s is not a valid %s image; it will be set aside",
                    video, FileName(out.name), s.format.upper())
        return Job(video, out, Action.REPLACE_BAD)
    if s.regenerate:
        return Job(video, out, Action.REGENERATE)
    if status is Existing.UNDERSIZED:
        predicted = _predict_width(video, s)
        if predicted is not None and predicted < s.min_width:
            log.info("%s: existing %s is %dpx wide (< %d), but a new sheet would only be "
                     "%dpx; keeping it", video, FileName(out.name), width, s.min_width, predicted)
            return Keep.CANT_REACH_MIN_WIDTH
        log.info("%s: existing %s is %dpx wide (< %d); will regenerate",
                 video, FileName(out.name), width, s.min_width)
        return Job(video, out, Action.REGENERATE)
    log.debug("%s: up to date (%s, %dpx wide)", video, FileName(out.name), width)
    return Keep.UP_TO_DATE


def _predict_width(video: Path, s: Settings) -> int | None:
    """Width a freshly rendered sheet would have, from ffprobe alone (no frame
    captures). None if it can't be predicted; the render will then surface
    whatever the problem is."""
    from .probe import probe
    from .sheet import predict_sheet_width
    from .timestamps import compute_stamps

    try:
        info = probe(video)
        n_caps = len(compute_stamps(info.duration, s))
    except VcsngError as e:
        log.debug("%s: can't predict sheet width: %s", video, e)
        return None
    return predict_sheet_width(info, n_caps, s)
