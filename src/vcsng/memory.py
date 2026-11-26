"""Peak memory use, for -v diagnostics. Standard library only (Unix)."""

from __future__ import annotations

import resource
import sys


def peak_usage() -> int:
    """This process's peak resident memory in bytes: a high-water mark for the
    whole run, so it only ever grows.

    ffmpeg's usage isn't reported: on Linux a child's peak includes the
    parent's memory at the moment it was spawned (before exec), so it would
    mostly echo vcsng's own figure."""
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return maxrss if sys.platform == "darwin" else maxrss * 1024  # macOS: bytes; Linux: KiB
