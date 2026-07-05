from fractions import Fraction

from vcsng.aspect import resolve_aspect


def test_explicit_fraction_passthrough():
    assert resolve_aspect(1920, 1080, None, Fraction(3, 2)) == Fraction(3, 2)


def test_keep_mode():
    assert resolve_aspect(720, 576, None, "keep") == Fraction(720, 576)


def test_auto_720x576():
    assert resolve_aspect(720, 576, None, "auto") == Fraction(4, 3)


def test_auto_1024x576():
    assert resolve_aspect(1024, 576, None, "auto") == Fraction(16, 9)


def test_auto_1920x1080():
    assert resolve_aspect(1920, 1080, None, "auto") == Fraction(16, 9)


def test_auto_352x288():
    assert resolve_aspect(352, 288, None, "auto") == Fraction(4, 3)


def test_auto_anamorphic_dar_override():
    assert resolve_aspect(720, 576, Fraction(16, 9), "auto") == Fraction(16, 9)


def test_auto_dar_matches_native_no_override():
    # dar equal to native ratio should not trigger the anamorphic branch,
    # falls through to the guess table.
    assert resolve_aspect(720, 576, Fraction(720, 576), "auto") == Fraction(4, 3)
