"""Terminal presentation of log output: timestamps, colour and spacing.

Modules keep logging as usual (`log.info("wrote %s (%dx%d)", path, w, h)`);
this module decides how records look. Each %-argument is coloured by what it
is: Paths and FileName strings as filenames, numbers and Figure strings as
figures, Strong strings in bold white. Message text takes the colour of its
level (or tone, see OK). The MUTED tone greys out the whole line, arguments
included, for things passed over (e.g. a sheet that's being kept).

A VcsngError argument is rendered from its parts: its own message in the error
colour (with its args styled as above) and any detail from an external tool in
the tool-output colour. On such a line the surrounding text stays plain, so
"video.mp4: " frames the error instead of blending into it.

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

from .errors import VcsngError


class FileName(str):
    """A string that names a file, e.g. a bare `path.name`."""


class Figure(str):
    """A pre-formatted measurement, e.g. a duration or a video timestamp."""


class Strong(str):
    """Text that should stand out from the rest of its line, e.g. a decision."""


# Pass as `extra=OK` to show an INFO message as a success.
OK = {"tone": "ok"}
# Pass as `extra=MUTED` to grey out a whole line, arguments and all.
MUTED = {"tone": "muted"}

# SGR codes. Bright ("light") variants of the 16 standard colours; 37 is the
# ordinary grey and 90 dark grey; "1;97" is bold white.
_PALETTE = {
    "time": "90",     # dark grey
    "muted": "90",    # dark grey
    "strong": "1;97", # bold white
    "file": "96",     # light cyan
    "figure": "95",   # light magenta
    "debug": "37",    # grey
    "warning": "93",  # light yellow
    "error": "91",    # light red
    "external": "93", # light yellow: output quoted from ffmpeg, the OS, ...
    "ok": "92",       # light green
}

_SPEC_RE = re.compile(r"%(?:\([^)]*\))?[#0 +-]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?([diouxXeEfFgGcrsa%])")
_UNIT_RE = re.compile(r"(?:px|ms|s|fps)(?![A-Za-z])")
_NUMERIC = set("diouxXeEfFgG")


def _role(arg: object) -> str | None:
    if isinstance(arg, (PurePath, FileName)):
        return "file"
    if isinstance(arg, Strong):
        return "strong"
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
        code = _PALETTE[role]
        # per line, so a multi-line value doesn't leave colour hanging in between
        return "\n".join(f"\x1b[{code}m{ln}\x1b[0m" if ln else ln for ln in text.split("\n"))

    def format(self, record: logging.LogRecord) -> str:
        stamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        body = self._body(record)
        if "\n" in body:  # continuation lines (e.g. tool output) align under the message
            msg = str(record.msg)
            indent = " " * (len(stamp) + 3 + len(msg) - len(msg.lstrip(" ")))
            body = body.replace("\n", "\n" + indent)
        line = f"{self.paint(f'[{stamp}]', 'time')} {body}"
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
        if not self.color or not args or isinstance(args, dict) or base == "muted":
            return self.paint(record.getMessage(), base)
        if base == "error" and any(isinstance(a, VcsngError) for a in args):
            base = None  # the error's own text carries the colour
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
            if isinstance(arg, VcsngError):
                out.append(self._error(arg))
                continue
            text = m.group(0) % arg
            if conv in _NUMERIC and (unit := _UNIT_RE.match(msg, pos)):
                text += unit.group(0)  # "1920px", "24.6s" read as one figure
                pos = unit.end()
            out.append(self.paint(text, _role(arg) or base))
        if args:
            raise TypeError("not all arguments converted")
        out.append(self.paint(msg[pos:], base))
        return "".join(out)


    def _error(self, e: VcsngError) -> str:
        if e.msg_args:
            text = self._render(e.msg, list(e.msg_args), "error")
        else:
            text = self.paint(e.msg, "error")
        if e.detail:
            text += ": " + self.paint(e.detail, "external")
        return text


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
