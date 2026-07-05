from dataclasses import replace

import pytest

from vcsng.config import Settings
from vcsng.errors import UsageError
from vcsng.timestamps import compute_stamps
from vcsng.values import Percent

DURATION = 303.188


def test_interval_default_end_offset():
    s = Settings(mode="interval", interval=20.0)
    stamps = compute_stamps(DURATION, s)
    assert len(stamps) == 14
    assert stamps[0] == 20.0
    assert stamps[-1] == 280.0
    assert stamps == [round(20.0 * k, 3) for k in range(1, 15)]


def test_interval_too_large_raises():
    s = Settings(mode="interval", interval=400.0)
    with pytest.raises(UsageError):
        compute_stamps(DURATION, s)


def test_numcaps_default_count_and_spacing():
    s = Settings(mode="numcaps", numcaps=16)
    stamps = compute_stamps(DURATION, s)
    assert len(stamps) == 16
    end = DURATION
    eo = end * 0.05
    limit = end - eo
    inc = limit / 16
    expected = sorted({round(inc * k, 3) for k in range(1, 17)})
    assert stamps == expected


def test_numcaps_one_is_centered():
    s = Settings(mode="numcaps", numcaps=1)
    stamps = compute_stamps(DURATION, s)
    assert len(stamps) == 1
    assert stamps[0] == round(DURATION / 2, 3)


def test_numcaps_less_than_one_raises():
    s = Settings(mode="numcaps", numcaps=0)
    with pytest.raises(UsageError):
        compute_stamps(DURATION, s)


def test_from_to_clamps_window():
    s = Settings(mode="numcaps", numcaps=1, from_time=10.0, to_time=20.0)
    stamps = compute_stamps(DURATION, s)
    assert stamps == [15.0]


def test_end_offset_absolute_seconds():
    # numcaps>1 so end_offset actually constrains the window (numcaps==1 is
    # a special case centered on the raw start/end, ignoring end_offset).
    s = Settings(mode="numcaps", numcaps=2, end_offset=10.0)
    stamps = compute_stamps(DURATION, s)
    end = DURATION
    limit = end - 10.0
    inc = limit / 2
    assert stamps == sorted({round(inc, 3), round(inc * 2, 3)})


def test_end_offset_percent():
    s = Settings(mode="numcaps", numcaps=2, end_offset=Percent(10.0))
    stamps = compute_stamps(DURATION, s)
    end = DURATION
    eo = end * 0.10
    limit = end - eo
    inc = limit / 2
    assert stamps == sorted({round(inc, 3), round(inc * 2, 3)})


def test_to_time_disables_end_offset():
    s = Settings(mode="numcaps", numcaps=1, to_time=100.0, end_offset=Percent(50.0))
    stamps = compute_stamps(DURATION, s)
    # end offset should NOT apply since to_time is set
    assert stamps == [50.0]


def test_manual_mode_only_manual_stamps():
    s = Settings(mode="manual", manual_stamps=(5.0, 15.5, 100.0))
    stamps = compute_stamps(DURATION, s)
    assert stamps == [5.0, 15.5, 100.0]


def test_manual_stamps_merged_with_interval_deduped_sorted():
    s = Settings(mode="interval", interval=20.0, manual_stamps=(20.0, 5.0, 500.0))
    stamps = compute_stamps(DURATION, s)
    # 20.0 already present from interval; 500.0 out of range (>= duration), dropped
    assert stamps[0] == 5.0
    assert stamps.count(20.0) == 1
    assert 500.0 not in stamps


def test_manual_stamps_filtered_to_valid_range():
    s = Settings(mode="manual", manual_stamps=(-5.0, 0.0, DURATION, DURATION + 10, 50.0))
    stamps = compute_stamps(DURATION, s)
    assert stamps == [0.0, 50.0]


def test_empty_window_raises():
    s = Settings(mode="numcaps", numcaps=1, from_time=100.0, to_time=100.0)
    with pytest.raises(UsageError):
        compute_stamps(DURATION, s)
