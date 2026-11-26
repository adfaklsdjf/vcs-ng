"""Integration tests requiring a real ffmpeg + synthetic video."""

from __future__ import annotations

import pytest
from PIL import Image

from vcsng.capture import capture_frames

pytestmark = pytest.mark.ffmpeg


def test_capture_frames_returns_ordered_frames(synthetic_video):
    stamps = [5.0, 10.0, 15.0]
    results = capture_frames(synthetic_video, stamps)

    assert len(results) == 3
    returned_stamps = [ts for ts, _ in results]
    assert returned_stamps == stamps

    for ts, img in results:
        assert img is not None
        assert isinstance(img, Image.Image)
        assert img.size == (320, 240)


def test_capture_frames_near_eof_does_not_raise(synthetic_video):
    stamps = [29.96]
    results = capture_frames(synthetic_video, stamps)

    assert len(results) == 1
    ts, img = results[0]
    assert ts == 29.96
    assert img is None or isinstance(img, Image.Image)


def test_capture_frames_on_capture_callback_fires_per_stamp(synthetic_video):
    stamps = [5.0, 10.0, 15.0]
    seen: list[float] = []
    capture_frames(synthetic_video, stamps, on_capture=seen.append)
    # one callback per stamp, exactly the stamps we asked for (order may vary
    # across parallel workers, so compare as sets)
    assert sorted(seen) == stamps


def test_capture_frames_shrinks_to_size(synthetic_video):
    [(_, img)] = capture_frames(synthetic_video, [5.0], size=(64, 36))
    assert img.size == (64, 36)
    assert img.mode == "RGBA"
