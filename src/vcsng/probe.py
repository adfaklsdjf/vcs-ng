"""ffprobe invocation and parsing into a normalized VideoInfo."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from .errors import MissingToolError, ProbeError


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    duration: float
    width: int
    height: int
    sar: Fraction | None
    dar: Fraction | None
    fps: float | None
    vcodec: str
    acodec: str | None
    audio_channels: int | None
    rotation: int
    file_size: int


def probe(path: Path) -> VideoInfo:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-of", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True,
        )
    except FileNotFoundError:
        raise MissingToolError("ffprobe not found; is ffmpeg installed and on PATH?") from None
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        snippet = stderr[-500:] if stderr else "(no stderr)"
        raise ProbeError("ffprobe failed on %s", path, detail=snippet)
    data = json.loads(proc.stdout.decode("utf-8", "replace"))
    return parse_probe(data, path, path.stat().st_size)


def _parse_fraction(value: str | None) -> Fraction | None:
    if not value or value in ("0:1", "N/A"):
        return None
    try:
        num, den = value.split(":")
        n, d = int(num), int(den)
    except (ValueError, AttributeError):
        return None
    if d == 0 or n == 0:
        return None
    return Fraction(n, d)


def _parse_duration_str(value: str) -> float:
    # HH:MM:SS.fffffffff
    h, m, s = value.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _parse_rate(value: str | None) -> float | None:
    if not value:
        return None
    try:
        num, den = value.split("/")
        n, d = float(num), float(den)
    except (ValueError, AttributeError):
        return None
    if d <= 0:
        return None
    return n / d


def _rotation_of(stream: dict) -> int:
    for sd in stream.get("side_data_list", []):
        if "rotation" in sd:
            try:
                return int(sd["rotation"]) % 360
            except (TypeError, ValueError):
                pass
    tags = stream.get("tags", {})
    if "rotate" in tags:
        try:
            return int(tags["rotate"]) % 360
        except (TypeError, ValueError):
            pass
    return 0


def parse_probe(data: dict, path: Path, file_size: int | None = None) -> VideoInfo:
    fmt = data.get("format", {})
    streams = data.get("streams", [])

    video_stream = None
    for s in streams:
        if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1:
            video_stream = s
            break
    if video_stream is None:
        raise ProbeError("%s: no video stream found", path)

    audio_stream = None
    for s in streams:
        if s.get("codec_type") == "audio":
            audio_stream = s
            break

    duration: float | None = None
    if "duration" in fmt:
        try:
            duration = float(fmt["duration"])
        except (TypeError, ValueError):
            duration = None
    if duration is None and "duration" in video_stream:
        try:
            duration = float(video_stream["duration"])
        except (TypeError, ValueError):
            duration = None
    if duration is None:
        tags = video_stream.get("tags", {})
        tag_val = tags.get("DURATION") or tags.get("DURATION-eng")
        if tag_val:
            try:
                duration = _parse_duration_str(tag_val)
            except (ValueError, AttributeError):
                duration = None
    if duration is None:
        raise ProbeError("%s: could not determine duration", path)

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    rotation = _rotation_of(video_stream)
    if rotation in (90, 270):
        width, height = height, width

    sar = _parse_fraction(video_stream.get("sample_aspect_ratio"))
    dar = _parse_fraction(video_stream.get("display_aspect_ratio"))

    avg_rate = video_stream.get("avg_frame_rate")
    fps = None
    if avg_rate and avg_rate != "0/0":
        fps = _parse_rate(avg_rate)
    if fps is None:
        fps = _parse_rate(video_stream.get("r_frame_rate"))

    file_size_val = file_size
    if file_size_val is None:
        if "size" in fmt:
            try:
                file_size_val = int(fmt["size"])
            except (TypeError, ValueError):
                file_size_val = 0
        else:
            file_size_val = 0

    audio_channels = None
    acodec = None
    if audio_stream is not None:
        acodec = audio_stream.get("codec_name")
        ch = audio_stream.get("channels")
        if ch is not None:
            try:
                audio_channels = int(ch)
            except (TypeError, ValueError):
                audio_channels = None

    return VideoInfo(
        path=path,
        duration=duration,
        width=width,
        height=height,
        sar=sar,
        dar=dar,
        fps=fps,
        vcodec=video_stream.get("codec_name", ""),
        acodec=acodec,
        audio_channels=audio_channels,
        rotation=rotation,
        file_size=file_size_val,
    )
