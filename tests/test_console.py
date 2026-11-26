"""Tests for console.py: timestamps, argument colouring and blank-line spacing."""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

import pytest

from vcsng import console
from vcsng.console import MUTED, OK, ConsoleFormatter, ConsoleHandler, Figure, FileName, Strong

STAMP = r"\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\] "


def record(msg, *args, level=logging.INFO, **extra):
    r = logging.LogRecord("vcsng", level, __file__, 1, msg, args, None)
    r.__dict__.update(extra)
    return r


def esc(code):
    return f"\x1b[{code}m"


def test_plain_output_has_iso_timestamp_and_no_escapes():
    line = ConsoleFormatter(color=False).format(record("wrote %s (%dpx)", Path("a.jpg"), 640))
    assert re.fullmatch(STAMP + r"wrote a\.jpg \(640px\)", line)


def test_arguments_coloured_by_role():
    line = ConsoleFormatter(color=True).format(
        record("%s: %s at %s, %d frames in %.1fs", Path("v.mp4"), FileName("v.jpg"),
               Figure("00:01:02"), 12, 3.25)
    )
    assert f"{esc(96)}v.mp4{esc(0)}" in line
    assert f"{esc(96)}v.jpg{esc(0)}" in line
    assert f"{esc(95)}00:01:02{esc(0)}" in line
    assert f"{esc(95)}12{esc(0)} frames" in line
    assert f"{esc(95)}3.2s{esc(0)}" in line  # unit suffix joins the figure


def test_message_text_takes_level_or_tone_colour():
    f = ConsoleFormatter(color=True)
    assert f"{esc(93)}moved {esc(0)}" in f.format(record("moved %s", Path("x"), level=logging.WARNING))
    assert f"{esc(91)}boom{esc(0)}" in f.format(record("boom", level=logging.ERROR))
    assert f"{esc(92)}wrote {esc(0)}" in f.format(record("wrote %s", Path("x"), **OK))
    assert f"{esc(37)}detail{esc(0)}" in f.format(record("detail", level=logging.DEBUG))


def test_strong_argument_is_bold_white():
    line = ConsoleFormatter(color=True).format(record("x; %s", Strong("will regenerate [3]")))
    assert f"{esc('1;97')}will regenerate [3]{esc(0)}" in line


def test_muted_tone_greys_out_arguments_too():
    line = ConsoleFormatter(color=True).format(
        record("%s is %dpx; keeping it", FileName("v.jpg"), 640, **MUTED))
    assert line.split(f"{esc(0)} ", 1)[1] == f"{esc(90)}v.jpg is 640px; keeping it{esc(0)}"


def test_percent_literal_and_bad_args_fall_back():
    f = ConsoleFormatter(color=True)
    assert "50% of 4" in re.sub(r"\x1b\[\d+m", "", f.format(record("50%% of %d", 4)))
    # A malformed call falls back to logging's own formatting, which raises as
    # usual (the handler then reports it the way logging always does).
    with pytest.raises(TypeError):
        f.format(record("only %d", 1, 2))


def run_handler(script):
    stream = io.StringIO()
    h = ConsoleHandler(stream, color=False)
    log = logging.getLogger("vcsng.test_console")
    log.addHandler(h)
    log.propagate = False
    log.setLevel(logging.INFO)
    try:
        script(log, h)
    finally:
        log.removeHandler(h)
        log.propagate = True
    return re.sub(STAMP, "", stream.getvalue())


def test_spacing_around_and_between_sections():
    def script(log, h):
        log.info("start")
        h.break_pending = True  # what console.section() does
        h.break_pending = True  # repeated requests collapse
        log.info("file one")
        h.break_pending = True
        log.info("file two")
        h.finish()

    assert run_handler(script) == "\nstart\n\nfile one\n\nfile two\n\n"


def test_no_messages_no_blank_lines():
    assert run_handler(lambda log, h: h.finish()) == ""


def test_module_helpers_drive_the_installed_handler():
    stream = io.StringIO()
    root = logging.getLogger()
    before = list(root.handlers), root.level
    try:
        console.setup(logging.INFO, stream)
        log = logging.getLogger("vcsng")
        log.info("a")
        console.section()
        log.info("b")
        console.finish()
    finally:
        root.handlers[:] = before[0]
        root.setLevel(before[1])
    assert re.sub(STAMP, "", stream.getvalue()) == "\na\n\nb\n\n"


def test_structured_error_parts():
    from vcsng.errors import ProbeError

    err = ProbeError("ffprobe failed on %s", Path("v.mp4"), detail="moov atom not found\nInvalid data")
    assert str(err) == "ffprobe failed on v.mp4: moov atom not found\nInvalid data"
    line = ConsoleFormatter(color=True).format(record("%s: %s", Path("v.mp4"), err, level=logging.ERROR))
    body = line.split(f"{esc(0)} ", 1)[1]  # past the timestamp
    assert body == (
        f"{esc(96)}v.mp4{esc(0)}: {esc(91)}ffprobe failed on {esc(0)}{esc(96)}v.mp4{esc(0)}: "
        f"{esc(93)}moov atom not found{esc(0)}\n{' ' * 22}{esc(93)}Invalid data{esc(0)}"
    )


def test_error_without_structure_is_all_red():
    from vcsng.errors import OutputError

    line = ConsoleFormatter(color=True).format(
        record("%s: %s", Path("v.mp4"), OutputError("plain message"), level=logging.ERROR))
    assert f"{esc(91)}plain message{esc(0)}" in line
    assert f"{esc(91)}failed{esc(0)}" in ConsoleFormatter(color=True).format(
        record("failed", level=logging.ERROR))


def test_continuation_lines_indent_under_message():
    line = ConsoleFormatter(color=False).format(record("  %s", "one\ntwo"))
    first, second = line.split("\n")
    assert second == " " * (first.index("one")) + "two"
