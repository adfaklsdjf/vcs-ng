"""Command-line entry point."""

from __future__ import annotations

import argparse
import itertools
import logging
import sys
import time
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
    p.add_argument("files", metavar="FILE", nargs="+", type=Path)

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
    for key in ("files", "profile", "config", "no_config", "verbose", "quiet"):
        overrides.pop(key, None)

    stamps = overrides.pop("stamp", None)
    if stamps is not None:
        manual = tuple(parse_timespec(s) for s in stamps)
        overrides["manual_stamps"] = manual
        if "numcaps" not in overrides and "interval" not in overrides:
            overrides["mode"] = "manual"

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

    try:
        overrides = _cli_overrides(args)
        _infer_format(overrides)

        if len(args.files) > 1:
            output_tpl = overrides.get("output")
            if output_tpl and "{stem}" not in output_tpl and "{name}" not in output_tpl:
                raise UsageError(
                    "output template would overwrite itself: needs {stem} or {name} "
                    "when processing multiple files"
                )

        from .config import build_settings

        settings = build_settings(
            overrides,
            config_path=args.config,
            profiles=tuple(args.profile),
            no_config=args.no_config,
        )
    except UsageError as e:
        parser.error(str(e))
        return 64  # pragma: no cover — parser.error exits

    worst = 0
    for file_path in args.files:
        try:
            worst = max(worst, _process_one(file_path, settings))
        except SkippedInput as e:
            log.info("%s: skipped: %s", file_path, e)
        except VcsngError as e:
            log.error("%s: %s", file_path, e)
            worst = max(worst, e.exit_code)
    return worst


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


def _process_one(file_path: Path, s) -> int:
    from .aspect import resolve_aspect
    from .capture import capture_frames
    from .output import resolve_output_path, save_sheet
    from .probe import probe
    from .sheet import build_sheet
    from .timestamps import compute_stamps
    from .values import pretty_stamp

    start = time.monotonic()
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
    img = build_sheet(info, frames, s, aspect)
    out_path = resolve_output_path(file_path, s)
    written = save_sheet(img, out_path, s)
    elapsed = time.monotonic() - start
    log.info(
        "wrote %s (%dx%d, %d captures, %.1fs)",
        written, img.width, img.height, len(stamps), elapsed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
