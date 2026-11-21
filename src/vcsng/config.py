"""Settings model, TOML config/profile loading, and layered merging.

Precedence: built-in defaults < config.toml < profiles (in order) < CLI flags.
Each layer is a flat dict of Settings field names -> already-parsed values;
`build_settings` folds them together with dataclasses.replace.
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, fields, replace
from fractions import Fraction
from importlib import resources
from pathlib import Path

from .errors import UsageError
from .values import (
    Percent,
    parse_aspect,
    parse_height,
    parse_percent_or_seconds,
    parse_timespec,
)

log = logging.getLogger("vcsng")

DEFAULT_EXTENSIONS: tuple[str, ...] = (
    "3gp", "asf", "avi", "divx", "f4v", "flv", "m2ts", "m4v", "mkv", "mov",
    "mp4", "mpeg", "mpg", "mts", "ogv", "rm", "rmvb", "webm", "wmv",
)


def parse_extensions(value) -> tuple[str, ...]:
    """Accept a list or comma-separated string; lowercase, strip leading dots."""
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
        raise UsageError(f"extensions: expected a list of strings, got {value!r}")
    exts = tuple(sorted({v.strip().lower().lstrip(".") for v in value if v.strip()}))
    if not exts:
        raise UsageError("extensions: list is empty")
    return exts


@dataclass(frozen=True)
class Settings:
    # capture
    mode: str = "numcaps"  # numcaps | interval | manual
    numcaps: int = 16
    interval: float = 300.0
    manual_stamps: tuple[float, ...] = ()
    from_time: float = 0.0
    to_time: float | None = None
    end_offset: float | Percent = Percent(5.0)
    skip_short: bool = False  # skip videos too short for the interval (default: 1 centered cap)
    # layout
    columns: int = 4
    height: int | Percent = Percent(100.0)
    padding: int = 2
    aspect: str | Fraction = "auto"  # auto | keep | explicit ratio
    shadows: bool = True
    timestamps: bool = True
    title: str | None = None
    # style (colors stay strings; render.parse_color interprets them)
    bg_heading: str = "#afcd7a"
    fg_heading: str = "black"
    bg_sign: str = "slategray"
    fg_sign: str = "black"
    bg_title: str = "white"
    fg_title: str = "black"
    bg_contact: str = "white"
    bg_tstamps: str = "black"
    fg_tstamps: str = "white"
    font_heading: str = "DejaVuSans"
    font_tstamps: str = "DejaVuSans"
    font_sign: str = "DejaVuSans"
    font_title: str = "DejaVuSans"
    pts_heading: int = 14
    pts_tstamps: int = 14
    pts_sign: int = 10
    pts_title: int = 33
    tstamp_pad_x: int = 5  # px between timestamp text and its bg box edge
    tstamp_pad_y: int = 5
    # output
    format: str = "png"  # png | jpeg
    quality: int = 92
    output: str | None = None  # -o template: {stem} {name} {dir} {ext}
    suffix: str = ""  # appended to {stem} before the extension, e.g. "-ss"
    overwrite: bool = False
    # general
    anonymous: bool = False
    credit: bool = True  # show the "Created with vcs-ng <version>" line
    signature: str = "Preview created by"
    username: str | None = None
    workers: int | None = None
    # directory scanning (-r / directory arguments)
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS
    min_width: int = 2000  # existing sheets narrower than this are regenerated


_META_STYLE = {
    "bg_all": ("bg_heading", "bg_sign", "bg_title", "bg_contact", "bg_tstamps"),
    "fg_all": ("fg_heading", "fg_sign", "fg_title", "fg_tstamps"),
    "font_all": ("font_heading", "font_tstamps", "font_sign", "font_title"),
}

# TOML section -> {key: parser}; parser=None keeps the raw value.
_STR = str
_INT = int
_BOOL = bool


def _typed(name: str, expected: type):
    def check(v):
        if not isinstance(v, expected) or (expected is int and isinstance(v, bool)):
            raise UsageError(f"config key {name!r}: expected {expected.__name__}, got {v!r}")
        return v

    return check


def _section_schema() -> dict[str, dict]:
    style: dict = {}
    for f in (
        "bg_heading", "fg_heading", "bg_sign", "fg_sign", "bg_title", "fg_title",
        "bg_contact", "bg_tstamps", "fg_tstamps",
        "font_heading", "font_tstamps", "font_sign", "font_title",
        "bg_all", "fg_all", "font_all",
    ):
        style[f] = _typed(f, str)
    for f in ("pts_heading", "pts_tstamps", "pts_sign", "pts_title",
              "tstamp_pad_x", "tstamp_pad_y"):
        style[f] = _typed(f, int)
    return {
        "capture": {
            "mode": _typed("mode", str),
            "numcaps": _typed("numcaps", int),
            "interval": parse_timespec,
            "from": parse_timespec,
            "to": parse_timespec,
            "end_offset": parse_percent_or_seconds,
            "skip_short": _typed("skip_short", bool),
        },
        "layout": {
            "columns": _typed("columns", int),
            "height": parse_height,
            "padding": _typed("padding", int),
            "aspect": parse_aspect,
            "shadows": _typed("shadows", bool),
            "timestamps": _typed("timestamps", bool),
        },
        "style": style,
        "output": {
            "format": _typed("format", str),
            "quality": _typed("quality", int),
            "output": _typed("output", str),
            "suffix": _typed("suffix", str),
            "overwrite": _typed("overwrite", bool),
        },
        "scan": {
            "extensions": parse_extensions,
            "min_width": _typed("min_width", int),
        },
        "general": {
            "anonymous": _typed("anonymous", bool),
            "credit": _typed("credit", bool),
            "signature": _typed("signature", str),
            "username": _typed("username", str),
            "workers": _typed("workers", int),
        },
    }


_KEY_RENAMES = {"from": "from_time", "to": "to_time"}


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path("~/.config").expanduser()
    return base / "vcsng"


def default_config_path() -> Path:
    return config_dir() / "config.toml"


def load_config_file(path: Path) -> dict:
    """Parse a TOML config/profile into a flat {field: parsed value} dict."""
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as e:
        raise UsageError(f"{path}: invalid TOML: {e}") from None
    schema = _section_schema()
    flat: dict = {}
    for section, keys in data.items():
        if section not in schema:
            log.warning("%s: unknown section [%s] ignored", path, section)
            continue
        if not isinstance(keys, dict):
            raise UsageError(f"{path}: [{section}] must be a table")
        for key, raw in keys.items():
            parser = schema[section].get(key)
            if parser is None:
                log.warning("%s: unknown key %s.%s ignored", path, section, key)
                continue
            flat[_KEY_RENAMES.get(key, key)] = parser(raw)
    _normalize_layer(flat)
    return flat


def _normalize_layer(flat: dict) -> None:
    """Expand *_all meta keys and infer capture mode within one layer."""
    for meta, targets in _META_STYLE.items():
        if meta in flat:
            val = flat.pop(meta)
            for t in targets:
                flat.setdefault(t, val)
    if "format" in flat:
        fmt = flat["format"].lower()
        if fmt == "jpg":
            fmt = "jpeg"
        if fmt not in ("png", "jpeg"):
            raise UsageError(f"unsupported format: {flat['format']!r}")
        flat["format"] = fmt
    if "mode" not in flat:
        if "interval" in flat:
            flat["mode"] = "interval"
        elif "numcaps" in flat:
            flat["mode"] = "numcaps"
    elif flat["mode"] not in ("numcaps", "interval", "manual"):
        raise UsageError(f"invalid capture mode: {flat['mode']!r}")


def profile_path(name: str) -> Path:
    """User profile shadows the built-in of the same name."""
    user = config_dir() / "profiles" / f"{name}.toml"
    if user.is_file():
        return user
    builtin = resources.files("vcsng.data.profiles") / f"{name}.toml"
    try:
        if builtin.is_file():
            with resources.as_file(builtin) as p:
                return Path(p)
    except (FileNotFoundError, ModuleNotFoundError):
        pass
    raise UsageError(f"profile not found: {name!r} (looked in {user.parent} and built-ins)")


_VALID_FIELDS = None


def build_settings(
    cli_overrides: dict,
    *,
    config_path: Path | None = None,
    profiles: tuple[str, ...] = (),
    no_config: bool = False,
) -> Settings:
    """Fold defaults < config file < profiles < CLI into a Settings."""
    global _VALID_FIELDS
    if _VALID_FIELDS is None:
        _VALID_FIELDS = {f.name for f in fields(Settings)}

    layers: list[dict] = []
    if no_config:
        log.debug("config: skipped (--no-config)")
    else:
        path = config_path or default_config_path()
        if path.is_file():
            layers.append(load_config_file(path))
            log.debug("config: loaded %s", path)
        elif config_path is not None:
            raise UsageError(f"config file not found: {config_path}")
        else:
            log.debug("config: no config file found at %s (using defaults)", path)
    for name in profiles:
        prof_path = profile_path(name)
        layers.append(load_config_file(prof_path))
        log.debug("config: loaded profile %r from %s", name, prof_path)

    cli = dict(cli_overrides)
    _normalize_layer(cli)
    layers.append(cli)

    settings = Settings()
    for layer in layers:
        unknown = set(layer) - _VALID_FIELDS
        if unknown:
            raise UsageError(f"unknown settings: {sorted(unknown)}")
        settings = replace(settings, **layer)
    return settings
