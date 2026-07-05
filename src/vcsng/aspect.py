"""Aspect ratio resolution, ported from the original vcs guess_aspect logic."""

from __future__ import annotations

from fractions import Fraction


def resolve_aspect(width: int, height: int, dar: Fraction | None, mode: str | Fraction) -> Fraction:
    if isinstance(mode, Fraction):
        return mode
    native = Fraction(width, height)
    if mode == "keep":
        return native
    if mode == "auto":
        if dar and dar != native:
            return dar
        if width == 352 and height in (240, 288, 480, 576):
            return Fraction(4, 3)
        if width in (704, 720, 480) and height in (480, 576):
            return Fraction(4, 3)
        if height in (720, 1080, 2160):
            return Fraction(16, 9)
        return native
    raise ValueError(f"unknown aspect mode: {mode!r}")
