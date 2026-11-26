"""Command-line entry point."""

from __future__ import annotations

import argparse
import itertools
import logging
import time
from collections import Counter
from pathlib import Path

from . import __version__, console
from .console import OK, Figure, FileName
from .errors import SkippedInput, UsageError, VcsngError
from .values import parse_aspect, parse_height, parse_percent_or_seconds, parse_timespec

log = logging.getLogger("vcsng")

_STYLE_KEYS = (
    "bg_heading", "fg_heading", "bg_sign", "fg_sign", "bg_title", "fg_title",
    "bg_contact", "bg_tstamps", "fg_tstamps", "bg_all", "fg_all",
    "font_heading", "font_tstamps", "font_sign", "font_title", "font_all",
)
_STYLE_PTS_KEYS = (
    "pts_heading", "pts_tstamps", "pts_sign", "pts_title", "tstamp_pad_x", "tstamp_pad_y",
)


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
        "sheets go next to each video, skipping videos that already have a valid sheet",
    )
    p.add_argument(
        "--extensions", type=str, default=argparse.SUPPRESS,
        help="comma-separated video extensions to look for when scanning directories",
    )
    p.add_argument(
        "--min-width", dest="min_width", type=int, default=argparse.SUPPRESS,
        help="when scanning, also regenerate existing sheets narrower than this many px "
        "(default: off)",
    )
    p.add_argument(
        "--regenerate", action="store_true", default=argparse.SUPPRESS,
        help="when scanning, regenerate every sheet, even ones that are up to date",
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
    p.add_argument(
        "--overwrite", action="store_true", default=argparse.SUPPRESS,
        help="replace existing sheets in place (default: rename the old one to NAME-old.EXT)",
    )

    p.add_argument("-j", "--workers", type=int, default=argparse.SUPPRESS)

    p.add_argument("--profile", action="append", dest="profile", default=[])
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--no-config", action="store_true", default=False)
    p.add_argument(
        "--init-config", action="store_true", default=False,
        help="write a config file listing every setting (commented out, at its default) "
        "to the default location, or to --config PATH, then exit",
    )

    verbosity = p.add_mutually_exclusive_group()
    verbosity.add_argument("-v", "--verbose", action="store_true", default=False)
    verbosity.add_argument("--quiet", action="store_true", default=False)

    p.add_argument("--version", action="version", version=f"vcsng {__version__}")

    return p


def _cli_overrides(args: argparse.Namespace) -> dict:
    overrides = vars(args).copy()
    for key in ("files", "recursive", "profile", "config", "no_config", "init_config",
                "verbose", "quiet"):
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
    console.setup(level)
    # Pillow (and other libraries) emit noisy DEBUG records like "STREAM b'IDAT'";
    # keep third-party loggers quiet even when our own logger is at DEBUG.
    logging.getLogger("PIL").setLevel(logging.WARNING)
    try:
        return _run(parser, args)
    finally:
        console.finish()


def _run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.init_config:
        return _init_config(parser, args.config)

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
        from .plan import Action, build_plan, collect_inputs

        inputs = collect_inputs(paths, settings, recursive=args.recursive)
        batch = len(inputs) > 1 or any(i.scanned for i in inputs)
        if batch:
            output_tpl = settings.output
            if output_tpl and "{stem}" not in output_tpl and "{name}" not in output_tpl:
                raise UsageError(
                    "output template would overwrite itself: needs {stem} or {name} "
                    "when processing multiple files"
                )
        plan = build_plan(inputs, settings)
    except UsageError as e:
        parser.error(str(e))
        return 64  # pragma: no cover — parser.error exits

    worst = 0
    tally: Counter[str] = Counter(up_to_date=plan.up_to_date, too_narrow=plan.too_narrow)
    failed: list[tuple[Path, VcsngError]] = []
    for path, err in plan.failed:
        log.error("%s: %s", path, err)
        failed.append((path, err))
        worst = max(worst, err.exit_code)
    if batch:
        _log_plan(plan)

    for i, job in enumerate(plan.jobs, 1):
        console.section()
        try:
            _run_job(job, settings, (i, len(plan.jobs)) if batch else None)
            tally["generated" if job.action is Action.NEW else "regenerated"] += 1
        except SkippedInput as e:
            log.info("%s: skipped: %s", job.video, e)
            tally["skipped"] += 1
        except VcsngError as e:
            log.error("%s: %s", job.video, e)
            failed.append((job.video, e))
            worst = max(worst, e.exit_code)

    if batch:
        console.section()
        _log_summary(tally, failed)
    return worst


def _init_config(parser: argparse.ArgumentParser, path: Path | None) -> int:
    from .config import default_config_path, write_example_config

    path = path or default_config_path()
    try:
        write_example_config(path)
    except UsageError as e:
        parser.error(str(e))
    except OSError as e:
        log.error("could not write %s: %s", path, e.strerror)
        return 1
    log.info("wrote %s", path, extra=OK)
    return 0


def _log_plan(plan) -> None:
    """One line between "found N videos" and execution: what's about to happen."""
    from .plan import Action

    n = len(plan.jobs)
    new = sum(j.action is Action.NEW for j in plan.jobs)
    counts = [(k, label) for k, label in (
        (new, "new"),
        (n - new, "replacing existing"),
        (plan.up_to_date, "up to date"),
        (plan.too_narrow, "kept, can't reach min-width"),
    ) if k]
    detail = f" ({_count_list(counts)})" if counts else ""
    log.info("generating %d contact sheet%s" + detail, n, "" if n == 1 else "s",
             *(k for k, _ in counts))


def _count_list(counts: list[tuple[int, str]]) -> str:
    """Format-string fragment "%d new, %d up to date" for [(k, label)...];
    counts stay log arguments so the console can style them as figures."""
    return ", ".join(f"%d {label.replace('%', '%%')}" for _, label in counts)


def _log_summary(tally: Counter, failed: list[tuple[Path, VcsngError]]) -> None:
    counts = [(tally[k], label) for k, label in (
        ("generated", "generated"),
        ("regenerated", "regenerated"),
        ("up_to_date", "up to date"),
        ("too_narrow", "kept (can't reach min-width)"),
        ("skipped", "skipped"),
    ) if tally[k]]
    counts.append((len(failed), "failed"))
    log.info("done: " + _count_list(counts), *(k for k, _ in counts),
             extra=None if failed else OK)  # green only for a clean run
    if failed:
        log.error("failed (%d):", len(failed))
        for path, err in failed:
            log.error("  %s: %s", path, err)


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


def _log_memory(stage: str) -> None:
    from .memory import peak_usage
    from .values import pretty_size

    if log.isEnabledFor(logging.DEBUG):
        log.debug("  peak memory after %s: %s", stage, Figure(pretty_size(peak_usage())))


def _render(file_path: Path, s, seq: tuple[int, int] | None):
    """Probe, capture, and compose the sheet. Returns (image, capture count).
    seq is (this job's number, job count) in a batch, shown as [N/M]."""
    from .aspect import resolve_aspect
    from .capture import capture_frames
    from .output import check_sheet_size
    from .probe import probe
    from .sheet import build_sheet, predict_sheet_size, thumb_size
    from .timestamps import compute_stamps
    from .values import pretty_stamp

    info = probe(file_path)
    stamps = compute_stamps(info.duration, s)
    _log_parameters(file_path, s, info, stamps)
    check_sheet_size(predict_sheet_size(info, len(stamps), s), s)

    total = len(stamps)
    progress = "[%d/%d] " if seq else ""
    log.info(progress + "thumbing %s: capturing %d thumbnails", *(seq or ()), file_path, total)
    counter = itertools.count(1)

    def on_capture(ts: float) -> None:
        log.info("  [%d/%d] capturing %s", next(counter), total, Figure(pretty_stamp(ts)))

    aspect = resolve_aspect(info.width, info.height, info.dar, s.aspect)
    frames = capture_frames(file_path, stamps, workers=s.workers, on_capture=on_capture,
                            size=thumb_size(s, info.height, aspect))
    _log_memory("capture")
    sheet = build_sheet(info, frames, s, aspect)
    _log_memory("composing")
    return sheet, total


def _run_job(job, s, seq: tuple[int, int] | None) -> None:
    """Render job.video and write it to job.out (setting aside junk first)."""
    from .output import save_sheet
    from .plan import Action

    start = time.monotonic()
    img, n_caps = _render(job.video, s, seq)
    if job.action is Action.REPLACE_BAD:
        _set_aside_bad(job.out)  # only once the new sheet is ready to write
    written = save_sheet(img, job.out, s)
    _log_memory("saving")
    elapsed = time.monotonic() - start
    log.info(
        "wrote %s (%dx%d, %d captures, %.1fs)",
        written, img.width, img.height, n_caps, elapsed, extra=OK,
    )


def _set_aside_bad(out: Path) -> None:
    from .errors import OutputError
    from .scan import set_aside

    try:
        moved = set_aside(out)
    except OSError as e:
        raise OutputError("could not rename %s", out, detail=str(e)) from None
    log.warning("moved %s -> %s", out, FileName(moved.name))


if __name__ == "__main__":
    raise SystemExit(main())
