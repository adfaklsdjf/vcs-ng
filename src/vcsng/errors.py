"""Error hierarchy. exit_code values follow BSD sysexits.h, like the original vcs."""


class VcsngError(Exception):
    """Base error. Like a log call, the message may take %-args, kept separate
    so the console can style them (filenames, figures); `detail` holds output
    from an external tool or the OS, shown after the message.

        raise OutputError("failed to write %s", target, detail=os_error_text)
    """

    exit_code = 70  # EX_SOFTWARE

    def __init__(self, msg: str, *args: object, detail: str | None = None):
        super().__init__(msg, *args)
        self.msg = msg
        self.msg_args = args
        self.detail = detail

    @property
    def message(self) -> str:
        """The message without detail."""
        return self.msg % self.msg_args if self.msg_args else self.msg

    def __str__(self) -> str:
        return f"{self.message}: {self.detail}" if self.detail else self.message


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
