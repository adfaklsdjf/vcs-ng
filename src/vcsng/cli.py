"""Command-line entry point."""

from __future__ import annotations

import argparse
import itertools
import logging
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

from . import __version__
from .errors import SkippedInput, UsageError, VcsngError
from .values import parse_aspect, parse_height, parse_percent_or_seconds, parse_timespec

log = logging.getLogger("vcsng")

_STYLE_KEYS = (
    "bg_heading", "fg_heading", "bg_sign", "fg_sign", "bg_title", "fg_title",
    "bg_contact", "bg_tstamps", "fg_tstamps", "bg_all", "fg_all",
    "font_heading", "font_tstamps", "font_sign", "font_title", "font_all",
)
_STYLE_PTS_KEYS = ("pts_heading", "pts_tstamps", "pts_sign", "pts_title")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vcsng",
        description="Generate a video contact sheet (thumbnail grid) from a video file.",
    )
    p.add_argument(
        "files", metavar="PATH", nargs="*", type=Path,
        help="video files and/or directories (directories are scanned recursively)",
    )
    p.add_argument(
        "-r", "--recursive", action="store_true", default=False,
        help="scan directories recursively for videos (current directory if no PATH given); "
        "sheets go next to each video, skipping ones that already exist and are at "
        "least --min-width wide",
    )
    p.add_argument(
        "--extensions", type=str, default=argparse.SUPPRESS,
        help="comma-separated video extensions to look for when scanning directories",
    )
    p.add_argument(
        "--min-width", dest="min_width", type=int, default=argparse.SUPPRESS,
        help="when scanning, regenerate existing sheets narrower than this (default 2000)",
    )

    caps = p.add_mutually_exclusive_group()
    caps.add_argument("-n", "--numcaps", type=int, default=argparse.SUPPRESS)
    caps.add_argument("-i", "--interval", type=parse_timespec, default=argparse.SUPPRESS)
    p.add_argument(
        "-S", "--stamp", action="append", dest="stamp", default=argparse.SUPPRESS,
        metavar="TIME",
    )

    p.add_argument(
        "--skip-short",
        dest="skip_short",
        action="store_true",
        default=argparse.SUPPRESS,
        help="skip videos too short for the capture interval "
        "(default: fall back to a single centered capture)",
    )

    p.add_argument("--from", dest="from_time", type=parse_timespec, default=argparse.SUPPRESS)
    p.add_argument("--to", dest="to_time", type=parse_timespec, default=argparse.SUPPRESS)
    p.add_argument(
        "--end-offset", dest="end_offset", type=parse_percent_or_seconds,
        default=argparse.SUPPRESS,
    )

    p.add_argument("-c", "--columns", type=int, default=argparse.SUPPRESS)
    p.add_argument("-H", "--height", type=parse_height, default=argparse.SUPPRESS)
    p.add_argument("-p", "--padding", type=int, default=argparse.SUPPRESS)
    p.add_argument("-a", "--aspect", type=parse_aspect, default=argparse.SUPPRESS)

    p.add_argument("--no-shadows", dest="shadows", action="store_false", default=argparse.SUPPRESS)
    p.add_argument(
        "--no-timestamps", dest="timestamps", action="store_false", default=argparse.SUPPRESS
    )
    p.add_argument("-T", "--title", type=str, default=argparse.SUPPRESS)

    for key in _STYLE_KEYS:
        flag = "--" + key.replace("_", "-")
        p.add_argument(flag, dest=key, type=str, default=argparse.SUPPRESS)
    for key in _STYLE_PTS_KEYS:
        flag = "--" + key.replace("_", "-")
        p.add_argument(flag, dest=key, type=int, default=argparse.SUPPRESS)

    p.add_argument("--anonymous", action="store_true", default=argparse.SUPPRESS)
    p.add_argument(
        "--no-credit",
        dest="credit",
        action="store_false",
        default=argparse.SUPPRESS,
        help="omit the 'Created with vcs-ng <version>' footer line",
    )
    p.add_argument("--username", type=str, default=argparse.SUPPRESS)
    p.add_argument("--signature", type=str, default=argparse.SUPPRESS)

    p.add_argument("-o", "--output", type=str, default=argparse.SUPPRESS)
    p.add_argument(
        "--suffix",
        type=str,
        default=argparse.SUPPRESS,
        help="appended to the filename before the extension, e.g. -ss",
    )
    p.add_argument(
        "-f", "--format", choices=["png", "jpeg", "jpg"], default=argparse.SUPPRESS
    )
    p.add_argument("-q", "--quality", type=int, default=argparse.SUPPRESS)
    p.add_argument("--overwrite", action="store_true", default=argparse.SUPPRESS)

    p.add_argument("-j", "--workers", type=int, default=argparse.SUPPRESS)

    p.add_argument("--profile", action="append", dest="profile", default=[])
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--no-config", action="store_true", default=False)

    verbosity = p.add_mutually_exclusive_group()
    verbosity.add_argument("-v", "--verbose", action="store_true", default=False)
    verbosity.add_argument("--quiet", action="store_true", default=False)

    p.add_argument("--version", action="version", version=f"vcsng {__version__}")

    return p


def _cli_overrides(args: argparse.Namespace) -> dict:
    overrides = vars(args).copy()
    for key in ("files", "recursive", "profile", "config", "no_config", "verbose", "quiet"):
        overrides.pop(key, None)

    stamps = overrides.pop("stamp", None)
    if stamps is not None:
        manual = tuple(parse_timespec(s) for s in stamps)
        overrides["manual_stamps"] = manual
        if "numcaps" not in overrides and "interval" not in overrides:
            overrides["mode"] = "manual"

    if "extensions" in overrides:
        from .config import parse_extensions

        overrides["extensions"] = parse_extensions(overrides["extensions"])

    if "format" in overrides and overrides["format"] == "jpg":
        overrides["format"] = "jpeg"

    return overrides


def _infer_format(overrides: dict) -> None:
    """If -o has a literal image suffix and no -f given, infer format from it."""
    if "format" in overrides:
        return
    output = overrides.get("output")
    if not output or "{ext}" in output:
        return
    suffix = Path(output).suffix.lower()
    if suffix == ".png":
        overrides["format"] = "png"
    elif suffix in (".jpg", ".jpeg"):
        overrides["format"] = "jpeg"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr)
    # Pillow (and other libraries) emit noisy DEBUG records like "STREAM b'IDAT'";
    # keep third-party loggers quiet even when our own logger is at DEBUG.
    logging.getLogger("PIL").setLevel(logging.WARNING)

    paths = list(args.files)
    if not paths:
        if not args.recursive:
            parser.error("no input files (use -r to scan the current directory)")
        paths = [Path(".")]

    try:
        overrides = _cli_overrides(args)
        _infer_format(overrides)

        from .config import build_settings

        settings = build_settings(
            overrides,
            config_path=args.config,
            profiles=tuple(args.profile),
            no_config=args.no_config,
        )
        jobs = _collect_jobs(paths, settings, recursive=args.recursive)
        if len(jobs) > 1 or any(scanned for _, scanned in jobs):
            output_tpl = settings.output
            if output_tpl and "{stem}" not in output_tpl and "{name}" not in output_tpl:
                raise UsageError(
                    "output template would overwrite itself: needs {stem} or {name} "
                    "when processing multiple files"
                )
    except UsageError as e:
        parser.error(str(e))
        return 64  # pragma: no cover — parser.error exits

    worst = 0
    tally: Counter[str] = Counter()
    failed: list[tuple[Path, str]] = []
    for file_path, scanned in jobs:
        try:
            if scanned:
                tally[_process_scanned(file_path, settings)] += 1
            else:
                worst = max(worst, _process_one(file_path, settings))
                tally["generated"] += 1
        except SkippedInput as e:
            log.info("%s: skipped: %s", file_path, e)
            tally["skipped"] += 1
        except VcsngError as e:
            log.error("%s: %s", file_path, e)
            failed.append((file_path, str(e)))
            worst = max(worst, e.exit_code)

    if len(jobs) > 1 or any(scanned for _, scanned in jobs):
        _log_summary(tally, failed)
    return worst


def _collect_jobs(
    paths: list[Path], s, *, recursive: bool
) -> list[tuple[Path, bool]]:
    """Expand directory arguments into (video, scanned=True) jobs; files pass through."""
    from .scan import iter_videos

    jobs: list[tuple[Path, bool]] = []
    for path in paths:
        if not path.is_dir():
            jobs.append((path, False))
            continue
        if not recursive:
            log.info("%s is a directory; scanning recursively", path)
        found = list(iter_videos(path, s.extensions))
        log.info("%s: found %d video%s", path, len(found), "" if len(found) == 1 else "s")
        jobs.extend((v, True) for v in found)
    return jobs


def _log_summary(tally: Counter, failed: list[tuple[Path, str]]) -> None:
    parts = [f"{tally[k]} {label}" for k, label in (
        ("generated", "generated"),
        ("regenerated", "regenerated"),
        ("up_to_date", "up to date"),
        ("skipped", "skipped"),
    ) if tally[k]]
    parts.append(f"{len(failed)} failed")
    log.info("done: %s", ", ".join(parts))
    if failed:
        log.error("failed (%d):", len(failed))
        for path, msg in failed:
            log.error("  %s: %s", path, msg)


def _log_parameters(file_path: Path, s, info, stamps) -> None:
    """Verbose dump of the effective settings used for this file."""
    from .values import Percent

    if s.mode == "interval":
        capture_desc = f"interval {s.interval:g}s"
    elif s.mode == "manual":
        capture_desc = f"manual ({len(s.manual_stamps)} stamps)"
    else:
        capture_desc = f"numcaps {s.numcaps}"

    height = f"{s.height.value:g}%" if isinstance(s.height, Percent) else f"{s.height}px"

    log.debug("processing %s", file_path)
    log.debug("  source: %dx%d, %.1fs, %s / %s", info.width, info.height,
              info.duration, info.vcodec, info.acodec or "no audio")
    log.debug("  capture: %s -> %d thumbnails, %d columns",
              capture_desc, len(stamps), s.columns)
    log.debug("  thumbnail height: %s (aspect %s)", height, s.aspect)
    log.debug("  format: %s (quality %d)", s.format, s.quality)
    log.debug("  shadows: %s, timestamps: %s", s.shadows, s.timestamps)
    log.debug("  fonts: heading=%s tstamps=%s sign=%s title=%s",
              s.font_heading, s.font_tstamps, s.font_sign, s.font_title)
    log.debug("  colors: bg_contact=%s bg_heading=%s fg_heading=%s "
              "bg_tstamps=%s fg_tstamps=%s",
              s.bg_contact, s.bg_heading, s.fg_heading, s.bg_tstamps, s.fg_tstamps)


def _render(file_path: Path, s):
    """Probe, capture, and compose the sheet. Returns (image, capture count)."""
    from .aspect import resolve_aspect
    from .capture import capture_frames
    from .probe import probe
    from .sheet import build_sheet
    from .timestamps import compute_stamps
    from .values import pretty_stamp

    info = probe(file_path)
    stamps = compute_stamps(info.duration, s)
    _log_parameters(file_path, s, info, stamps)

    total = len(stamps)
    log.info("%s: capturing %d thumbnails", file_path.name, total)
    counter = itertools.count(1)

    def on_capture(ts: float) -> None:
        log.info("  [%d/%d] capturing %s", next(counter), total, pretty_stamp(ts))

    frames = capture_frames(file_path, stamps, workers=s.workers, on_capture=on_capture)
    aspect = resolve_aspect(info.width, info.height, info.dar, s.aspect)
    return build_sheet(info, frames, s, aspect), total


def _process_one(file_path: Path, s, out_path: Path | None = None, before_save=None) -> int:
    from .output import resolve_output_path, save_sheet

    start = time.monotonic()
    img, n_caps = _render(file_path, s)
    out_path = out_path or resolve_output_path(file_path, s)
    if before_save is not None:
        before_save()
    written = save_sheet(img, out_path, s)
    elapsed = time.monotonic() - start
    log.info(
        "wrote %s (%dx%d, %d captures, %.1fs)",
        written, img.width, img.height, n_caps, elapsed,
    )
    return 0


def _process_scanned(file_path: Path, s) -> str:
    """Directory-scan mode: sheet goes next to the video and is only (re)made when
    missing, narrower than s.min_width, or not a valid image. Returns a tally key."""
    from .errors import OutputError
    from .output import resolve_output_path
    from .scan import Existing, check_existing, set_aside

    out = resolve_output_path(file_path, s, base_dir=file_path.parent)
    status, width = check_existing(out, s.format, s.min_width)

    if status is Existing.OK and not s.overwrite:
        log.debug("%s: up to date (%s, %dpx wide)", file_path, out.name, width)
        return "up_to_date"
    if status is Existing.UNDERSIZED:
        log.info("%s: existing %s is %dpx wide (< %d); regenerating",
                 file_path, out.name, width, s.min_width)
    elif status is Existing.BAD:
        log.warning("%s: existing %s is not a valid %s image; it will be set aside",
                    file_path, out.name, s.format.upper())

    def set_aside_bad() -> None:
        try:
            moved = set_aside(out)
        except OSError as e:
            raise OutputError(f"could not rename {out}: {e}") from None
        log.warning("moved %s -> %s", out, moved.name)

    _process_one(
        file_path,
        replace(s, overwrite=True),
        out_path=out,
        before_save=set_aside_bad if status is Existing.BAD else None,
    )
    return "generated" if status is Existing.MISSING else "regenerated"


if __name__ == "__main__":
    raise SystemExit(main())
