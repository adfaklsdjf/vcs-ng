"""Value types and parse/format helpers shared across modules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from .errors import UsageError


@dataclass(frozen=True)
class Percent:
    value: float

    def resolve(self, base: float) -> float:
        return base * self.value / 100.0


_COLON_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$")
_UNITS_RE = re.compile(
    r"^(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s?)?$",
    re.IGNORECASE,
)


def parse_timespec(value: str | int | float) -> float:
    """Parse '300', '90.5', '20s', '5m30s', '1h3m90', '1:02:03.5' into seconds.

    Trailing unitless numbers count as seconds ('1h90' == 3690), matching vcs.
    """
    if isinstance(value, (int, float)):
        if value < 0:
            raise UsageError(f"negative time: {value}")
        return float(value)
    s = value.strip()
    if not s:
        raise UsageError("empty time specification")
    if ":" in s:
        m = _COLON_RE.match(s)
        if not m:
            raise UsageError(f"invalid timestamp: {value!r}")
        h, mins, secs = m.groups()
        return (int(h) if h else 0) * 3600 + int(mins) * 60 + float(secs)
    try:
        return float(s)
    except ValueError:
        pass
    m = _UNITS_RE.match(s)
    if not m or not any(m.groups()):
        raise UsageError(f"invalid time specification: {value!r}")
    h, mins, secs = m.groups()
    return (float(h) if h else 0) * 3600 + (float(mins) if mins else 0) * 60 + (
        float(secs) if secs else 0
    )


def parse_percent_or_seconds(value: str | int | float) -> float | Percent:
    """'5%' -> Percent(5); anything else -> seconds via parse_timespec."""
    if isinstance(value, str) and value.strip().endswith("%"):
        try:
            return Percent(float(value.strip()[:-1]))
        except ValueError:
            raise UsageError(f"invalid percentage: {value!r}") from None
    return parse_timespec(value)


def parse_height(value: str | int) -> int | Percent:
    """'330' or 330 -> pixels; '50%' -> Percent(50)."""
    if isinstance(value, int):
        h: int | Percent = value
    else:
        s = value.strip()
        if s.endswith("%"):
            try:
                h = Percent(float(s[:-1]))
            except ValueError:
                raise UsageError(f"invalid height: {value!r}") from None
        else:
            try:
                h = int(s)
            except ValueError:
                raise UsageError(f"invalid height: {value!r}") from None
    if (isinstance(h, int) and h <= 0) or (isinstance(h, Percent) and h.value <= 0):
        raise UsageError(f"height must be positive: {value!r}")
    return h


def parse_aspect(value: str | int | float) -> str | Fraction:
    """'auto' | 'keep' | '16:9' | '16/9' | 1.777 -> mode string or Fraction."""
    if isinstance(value, (int, float)):
        if value <= 0:
            raise UsageError(f"aspect ratio must be positive: {value!r}")
        return Fraction(value).limit_denominator(10000)
    s = value.strip().lower()
    if s in ("auto", "keep"):
        return s
    m = re.match(r"^(\d+(?:\.\d+)?)[:/](\d+(?:\.\d+)?)$", s)
    try:
        if m:
            frac = Fraction(float(m.group(1)) / float(m.group(2))).limit_denominator(10000)
        else:
            frac = Fraction(float(s)).limit_denominator(10000)
    except (ValueError, ZeroDivisionError):
        raise UsageError(f"invalid aspect ratio: {value!r}") from None
    if frac <= 0:
        raise UsageError(f"aspect ratio must be positive: {value!r}")
    return frac


def pretty_stamp(seconds: float) -> str:
    """Thumbnail timestamp text: '00:20.00', '04:40.00', '1:02:03.50' (>=1h)."""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h >= 1:
        return f"{int(h)}:{int(m):02d}:{s:05.2f}"
    return f"{int(m):02d}:{s:05.2f}"


def pretty_duration(seconds: float) -> str:
    """Heading 'Length' text: '05:03', '1:05:03' (>=1h). Decimals dropped."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def pretty_size(num_bytes: int) -> str:
    """'37.15 MiB' style, matching the original's heading."""
    n = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.2f} {unit}"
        n /= 1024
    raise AssertionError("unreachable")
