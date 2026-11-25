"""Terminal presentation of log output: timestamps, colour and spacing.

Modules keep logging as usual (`log.info("wrote %s (%dx%d)", path, w, h)`);
this module decides how records look. Each %-argument is coloured by what it
is: Paths and FileName strings as filenames, numbers and Figure strings as
figures. Message text takes the colour of its level (or tone, see OK).

Spacing: a blank line precedes the first message and follows the last, and
section() asks for one before the next message (e.g. between files). Blank
lines never double up, and a run that logs nothing prints nothing.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from datetime import datetime
from pathlib import PurePath
from typing import TextIO


class FileName(str):
    """A string that names a file, e.g. a bare `path.name`."""


class Figure(str):
    """A pre-formatted measurement, e.g. a duration or a video timestamp."""


# Pass as `extra=OK` to show an INFO message as a success.
OK = {"tone": "ok"}

# SGR codes. Bright ("light") variants of the 16 standard colours; 37 is the
# ordinary grey. White (97) and dark grey (90) are deliberately unused for now.
_PALETTE = {
    "time": "37",
    "file": "96",     # light cyan
    "figure": "95",   # light magenta
    "debug": "37",    # grey
    "warning": "93",  # light yellow
    "error": "91",    # light red
    "ok": "92",       # light green
}

_SPEC_RE = re.compile(r"%(?:\([^)]*\))?[#0 +-]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?([diouxXeEfFgGcrsa%])")
_UNIT_RE = re.compile(r"(?:px|ms|s|fps)(?![A-Za-z])")
_NUMERIC = set("diouxXeEfFgG")


def _role(arg: object) -> str | None:
    if isinstance(arg, (PurePath, FileName)):
        return "file"
    if isinstance(arg, Figure) or (isinstance(arg, (int, float)) and not isinstance(arg, bool)):
        return "figure"
    return None


class ConsoleFormatter(logging.Formatter):
    def __init__(self, color: bool):
        super().__init__()
        self.color = color

    def paint(self, text: str, role: str | None) -> str:
        if not (self.color and role and text):
            return text
        return f"\x1b[{_PALETTE[role]}m{text}\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        stamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        line = f"{self.paint(f'[{stamp}]', 'time')} {self._body(record)}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line

    def _base_role(self, record: logging.LogRecord) -> str | None:
        if record.levelno >= logging.ERROR:
            return "error"
        if record.levelno >= logging.WARNING:
            return "warning"
        if record.levelno < logging.INFO:
            return "debug"
        return getattr(record, "tone", None)

    def _body(self, record: logging.LogRecord) -> str:
        base = self._base_role(record)
        args = record.args
        if not self.color or not args or isinstance(args, dict):
            return self.paint(record.getMessage(), base)
        try:
            return self._render(str(record.msg), list(args), base)
        except (TypeError, ValueError, IndexError):  # malformed call; show it plainly
            return self.paint(record.getMessage(), base)

    def _render(self, msg: str, args: list, base: str | None) -> str:
        out: list[str] = []
        pos = 0
        for m in _SPEC_RE.finditer(msg):
            out.append(self.paint(msg[pos:m.start()], base))
            pos = m.end()
            conv = m.group(1)
            if conv == "%":
                out.append(self.paint("%", base))
                continue
            arg = args.pop(0)
            text = m.group(0) % arg
            if conv in _NUMERIC and (unit := _UNIT_RE.match(msg, pos)):
                text += unit.group(0)  # "1920px", "24.6s" read as one figure
                pos = unit.end()
            out.append(self.paint(text, _role(arg) or base))
        if args:
            raise TypeError("not all arguments converted")
        out.append(self.paint(msg[pos:], base))
        return "".join(out)


class ConsoleHandler(logging.StreamHandler):
    """StreamHandler that adds the blank lines described in the module doc."""

    def __init__(self, stream: TextIO, color: bool):
        super().__init__(stream)
        self.setFormatter(ConsoleFormatter(color))
        self.break_pending = True  # blank line before the first message
        self.wrote = False

    def emit(self, record: logging.LogRecord) -> None:
        if self.break_pending:
            self.stream.write("\n")
            self.break_pending = False
        super().emit(record)
        self.wrote = True

    def finish(self) -> None:
        with self.lock:
            if self.wrote:
                self.stream.write("\n")
                self.flush()
            self.wrote = False


_handler: ConsoleHandler | None = None


def use_color(stream: TextIO) -> bool:
    """https://no-color.org and FORCE_COLOR, else colour only on a terminal."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


def setup(level: int, stream: TextIO | None = None) -> None:
    """Route the root logger through a ConsoleHandler on stream (stderr)."""
    global _handler
    stream = stream or sys.stderr
    _handler = ConsoleHandler(stream, use_color(stream))
    root = logging.getLogger()
    for h in [h for h in root.handlers if isinstance(h, ConsoleHandler)]:
        root.removeHandler(h)  # main() run twice in one process (tests)
    root.addHandler(_handler)
    root.setLevel(level)


def section() -> None:
    """Put a blank line before the next message, if one is logged."""
    if _handler is not None:
        with _handler.lock:
            _handler.break_pending = True


def finish() -> None:
    """Blank line after the last message; call once on the way out."""
    if _handler is not None:
        _handler.finish()
