from fractions import Fraction

import pytest

from vcsng.errors import UsageError
from vcsng.values import (
    Percent,
    parse_aspect,
    parse_height,
    parse_percent_or_seconds,
    parse_timespec,
    pretty_duration,
    pretty_size,
    pretty_stamp,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("300", 300.0),
        ("90.5", 90.5),
        ("20s", 20.0),
        ("5m30s", 330.0),
        ("1h3m90", 3870.0),
        ("1:02:03.5", 3723.5),
    ],
)
def test_parse_timespec_valid(value, expected):
    assert parse_timespec(value) == expected


@pytest.mark.parametrize("value", ["", "s", ".11s", "1ss"])
def test_parse_timespec_invalid(value):
    with pytest.raises(UsageError):
        parse_timespec(value)


def test_parse_timespec_numeric_passthrough():
    assert parse_timespec(300) == 300.0
    assert parse_timespec(90.5) == 90.5


def test_parse_timespec_negative():
    with pytest.raises(UsageError):
        parse_timespec(-1)


def test_parse_percent_or_seconds():
    assert parse_percent_or_seconds("5%") == Percent(5.0)
    assert parse_percent_or_seconds("20s") == 20.0


@pytest.mark.parametrize(
    "value,expected",
    [
        (330, 330),
        ("330", 330),
        ("50%", Percent(50.0)),
    ],
)
def test_parse_height_valid(value, expected):
    assert parse_height(value) == expected


@pytest.mark.parametrize("value", [0, -5, "x"])
def test_parse_height_invalid(value):
    with pytest.raises(UsageError):
        parse_height(value)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("auto", "auto"),
        ("keep", "keep"),
        ("16:9", Fraction(16, 9)),
        ("16/9", Fraction(16, 9)),
        ("1.777", Fraction(1.777).limit_denominator(10000)),
    ],
)
def test_parse_aspect_valid(value, expected):
    assert parse_aspect(value) == expected


@pytest.mark.parametrize("value", ["0", "x"])
def test_parse_aspect_invalid(value):
    with pytest.raises(UsageError):
        parse_aspect(value)


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (20, "00:20.00"),
        (280, "04:40.00"),
        (3723.5, "1:02:03.50"),
    ],
)
def test_pretty_stamp(seconds, expected):
    assert pretty_stamp(seconds) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (303, "05:03"),
        (3903, "1:05:03"),
    ],
)
def test_pretty_duration(seconds, expected):
    assert pretty_duration(seconds) == expected


@pytest.mark.parametrize(
    "num_bytes,expected",
    [
        (38943766, "37.14 MiB"),
        (512, "512 B"),
        (2048, "2.00 KiB"),
    ],
)
def test_pretty_size(num_bytes, expected):
    assert pretty_size(num_bytes) == expected
