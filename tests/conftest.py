"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
import subprocess

import pytest

HAS_FFMPEG = shutil.which("ffmpeg") is not None


@pytest.fixture(scope="session")
def synthetic_video(tmp_path_factory):
    """A short synthetic 30s test video generated via ffmpeg's lavfi sources."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg not found on PATH")
    out_dir = tmp_path_factory.mktemp("synthetic_video")
    out_path = out_dir / "out.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc2=duration=30:size=320x240:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )
    return out_path
