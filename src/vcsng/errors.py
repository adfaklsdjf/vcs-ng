"""Error hierarchy. exit_code values follow BSD sysexits.h, like the original vcs."""


class VcsngError(Exception):
    exit_code = 70  # EX_SOFTWARE


class UsageError(VcsngError):
    exit_code = 64  # EX_USAGE


class InputError(VcsngError):
    exit_code = 66  # EX_NOINPUT


class SkippedInput(VcsngError):
    """Input intentionally skipped (not an error), e.g. --skip-short."""

    exit_code = 0


class ProbeError(InputError):
    pass


class MissingToolError(VcsngError):
    exit_code = 69  # EX_UNAVAILABLE


class CaptureError(VcsngError):
    exit_code = 70


class OutputError(VcsngError):
    exit_code = 73  # EX_CANTCREAT
