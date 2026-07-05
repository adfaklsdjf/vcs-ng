"""Compute the list of timestamps to capture for a video."""

from __future__ import annotations

from .config import Settings
from .errors import UsageError
from .values import Percent


def compute_stamps(duration: float, s: Settings) -> list[float]:
    start = max(0.0, s.from_time)
    end = min(duration, s.to_time) if s.to_time is not None else duration

    if s.to_time is None:
        eo = s.end_offset.resolve(end) if isinstance(s.end_offset, Percent) else s.end_offset
    else:
        eo = 0.0
    limit = end - eo

    if limit <= start:
        raise UsageError(
            f"empty capture window: start={start}, limit={limit} (duration={duration})"
        )

    stamps: list[float] = []

    if s.mode == "interval":
        if s.interval >= duration:
            raise UsageError(f"interval {s.interval} >= duration {duration}")
        k = 1
        stamp = start + k * s.interval
        while stamp <= limit:
            stamps.append(stamp)
            k += 1
            stamp = start + k * s.interval
    elif s.mode == "numcaps":
        if s.numcaps < 1:
            raise UsageError(f"numcaps must be >= 1: {s.numcaps}")
        if s.numcaps == 1:
            stamps.append(start + (end - start) / 2)
        else:
            inc = (limit - start) / s.numcaps
            for k in range(1, s.numcaps + 1):
                stamps.append(start + inc * k)
    elif s.mode == "manual":
        pass
    else:
        raise UsageError(f"unknown capture mode: {s.mode!r}")

    stamps.extend(s.manual_stamps)
    stamps = [round(t, 3) for t in stamps if 0 <= t < duration]
    return sorted(set(stamps))
