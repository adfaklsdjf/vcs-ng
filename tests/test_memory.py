"""peak_usage reports bytes on every platform (ru_maxrss units differ)."""

from vcsng.memory import peak_usage


def test_peak_usage_is_plausible_bytes():
    assert 10 * 2**20 < peak_usage() < 64 * 2**30  # a Python process: > 10 MiB, < 64 GiB
