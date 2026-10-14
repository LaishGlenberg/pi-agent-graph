"""Shell / OS quoting helpers.

Every string that ends up inside a generated command line goes through one of
these so quoting is defined in exactly one place.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence


def quote_posix(value: str) -> str:
    """Single-quote *value* for a POSIX shell.

    The inverse property holds: ``shlex.split(quote_posix(v), posix=True) == [v]``.
    """
    return "'" + value.replace("'", "'\\''") + "'"


def join_posix(argv: Sequence[str]) -> str:
    """Render *argv* as a single POSIX shell command string."""
    return " ".join(quote_posix(token) for token in argv)


def quote_windows(argv: Sequence[str]) -> str:
    """Render *argv* as a Windows ``cmd.exe`` command line."""
    return subprocess.list2cmdline(list(argv))


def quote_applescript(value: str) -> str:
    """Escape *value* for embedding inside an AppleScript double-quoted string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
