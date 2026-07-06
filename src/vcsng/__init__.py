from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vcs-ng")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0+unknown"

PROGRAM_SIGNATURE = f"vcs-ng {__version__}"
