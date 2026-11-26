"""peak_usage reports bytes on every platform (ru_maxrss units differ)."""

from vcsng.memory import peak_usage


def test_peak_usage_is_plausible_bytes():
    own, child = peak_usage()
    assert 10 * 2**20 < own < 64 * 2**30  # a Python process: > 10 MiB, < 64 GiB
    assert child >= 0
