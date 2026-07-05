import json
from fractions import Fraction
from pathlib import Path

import pytest

from vcsng.errors import ProbeError
from vcsng.probe import VideoInfo, parse_probe

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_parse_real_webm_fixture():
    data = load_fixture("hank-green-webm.json")
    info = parse_probe(data, Path("hank-green.webm"))
    assert info.duration == pytest.approx(303.188)
    assert info.width == 1920
    assert info.height == 1080
    assert info.sar == Fraction(1, 1)
    assert info.dar == Fraction(16, 9)
    assert info.fps == 60.0
    assert info.vcodec == "av1"
    assert info.acodec == "opus"
    assert info.audio_channels == 2
    assert info.rotation == 0
    assert info.file_size == 38943766


def _video_stream(**overrides):
    stream = {
        "index": 0,
        "codec_name": "h264",
        "codec_type": "video",
        "width": 1280,
        "height": 720,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "duration": "10.0",
        "disposition": {"attached_pic": 0},
        "tags": {},
    }
    stream.update(overrides)
    return stream


def test_rotation_via_side_data_list():
    stream = _video_stream(side_data_list=[{"side_data_type": "Display Matrix", "rotation": -90}])
    data = {"streams": [stream], "format": {"duration": "10.0"}}
    info = parse_probe(data, Path("rotated.mp4"))
    assert info.rotation == 270
    # width/height swapped since rotation is 90/270
    assert info.width == 720
    assert info.height == 1280


def test_rotation_via_tags():
    stream = _video_stream(tags={"rotate": "180"})
    data = {"streams": [stream], "format": {"duration": "10.0"}}
    info = parse_probe(data, Path("rotated180.mp4"))
    assert info.rotation == 180
    assert info.width == 1280
    assert info.height == 720


def test_no_audio_stream():
    stream = _video_stream()
    data = {"streams": [stream], "format": {"duration": "10.0"}}
    info = parse_probe(data, Path("silent.mp4"), file_size=1234)
    assert info.acodec is None
    assert info.audio_channels is None
    assert info.file_size == 1234


def test_attached_pic_video_stream_skipped():
    cover = _video_stream(codec_name="mjpeg", disposition={"attached_pic": 1})
    real = _video_stream()
    data = {"streams": [cover, real], "format": {"duration": "10.0"}}
    info = parse_probe(data, Path("with_cover.mp4"))
    assert info.vcodec == "h264"


def test_missing_duration_raises_probe_error():
    stream = _video_stream()
    del stream["duration"]
    data = {"streams": [stream], "format": {}}
    with pytest.raises(ProbeError):
        parse_probe(data, Path("noduration.mp4"))


def test_no_video_stream_raises_probe_error():
    data = {"streams": [{"codec_type": "audio", "codec_name": "aac"}], "format": {"duration": "1"}}
    with pytest.raises(ProbeError):
        parse_probe(data, Path("audio_only.mp4"))


def test_duration_from_stream_tags_hhmmss():
    stream = _video_stream(tags={"DURATION": "00:05:03.167000000"})
    del stream["duration"]
    data = {"streams": [stream], "format": {}}
    info = parse_probe(data, Path("tagged.mp4"))
    assert info.duration == pytest.approx(303.167)


def test_sar_dar_missing_or_zero_treated_as_none():
    stream = _video_stream(sample_aspect_ratio="0:1", display_aspect_ratio="N/A")
    data = {"streams": [stream], "format": {"duration": "10.0"}}
    info = parse_probe(data, Path("nosar.mp4"))
    assert info.sar is None
    assert info.dar is None


def test_fps_falls_back_to_r_frame_rate_when_avg_is_zero():
    stream = _video_stream(avg_frame_rate="0/0", r_frame_rate="25/1")
    data = {"streams": [stream], "format": {"duration": "10.0"}}
    info = parse_probe(data, Path("fallbackfps.mp4"))
    assert info.fps == 25.0
