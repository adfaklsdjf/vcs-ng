"""Peak memory use, for -v diagnostics. Standard library only (Unix)."""

from __future__ import annotations

import resource
import sys


def _to_bytes(maxrss: int) -> int:
    # ru_maxrss is bytes on macOS, KiB on Linux
    return maxrss if sys.platform == "darwin" else maxrss * 1024


def peak_usage() -> tuple[int, int]:
    """Peak resident memory in bytes: (this process, the largest single child
    process so far, e.g. one ffmpeg). Both are high-water marks for the whole
    run, so they only ever grow."""
    own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    child = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return _to_bytes(own), _to_bytes(child)
