"""The ``terminal`` backend and its pure invocation helpers.

The helpers (:func:`windows_wt_command`, :func:`linux_emulator_command`,
:func:`macos_osascript_command`, ...) build argv lists without side effects and
are the unit-test surface. :class:`TerminalBackend` composes them and spawns
detached processes.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ..errors import LaunchError
from ..models import Agent
from ..quoting import join_posix, quote_applescript, quote_posix, quote_windows
from .types import LaunchOptions, LaunchResult

Which = Callable[[str], str | None]

_NEWLINE_RE = re.compile(r"\s*\n\s*")


def normalize_windows_args(argv: Sequence[str]) -> list[str]:
    """Collapse embedded newlines so *argv* fits on one ``cmd.exe`` line.

    ``cmd.exe`` batch files cannot carry a newline inside an argument, and
    multi-line system prompts are common here. The change is cosmetic.
    """
    return [_NEWLINE_RE.sub(" ", token) for token in argv]


LINUX_EMULATORS: tuple[str, ...] = (
    "wt",
    "gnome-terminal",
    "konsole",
    "xfce4-terminal",
    "kitty",
    "alacritty",
    "xterm",
)


# -- pure invocation builders --------------------------------------------
def windows_wt_command(
    cmd: Sequence[str], name: str, cwd: str | None = None
) -> list[str]:
    """Windows Terminal invocation for *cmd*.

    ``wt`` parses its own command line and treats ``;`` as a command separator.
    The Windows backend therefore never hands it a raw agent command: it
    writes a ``.cmd`` script and passes ``cmd /k <script>`` instead. This
    helper still collapses embedded newlines (also separators to ``wt``) so
    any caller that does pass a raw command stays safe.
    """
    argv = ["wt", "-w", "0", "nt", "--title", name]
    if cwd:
        argv += ["-d", cwd]
    return argv + normalize_windows_args(cmd)


def windows_start_command(script_path: str | Path) -> list[str]:
    """``cmd /c start`` wrapper around a generated ``.cmd`` script."""
    return ["cmd", "/c", "start", "", "cmd", "/k", str(script_path)]


def build_windows_script(cmd: Sequence[str], cwd: str | None = None) -> str:
    """Render a ``.cmd`` script that runs *cmd* (used when ``wt`` is absent)."""
    lines = ["@echo off"]
    if cwd:
        lines.append(f'cd /d "{cwd}"')
    lines.append(quote_windows(normalize_windows_args(cmd)))
    return "\r\n".join(lines) + "\r\n"


def write_temp_script(content: str, suffix: str) -> Path:
    """Write *content* to a fresh temp file and return its path."""
    directory = Path(tempfile.mkdtemp(prefix="pi-agent-graph-"))
    path = directory / f"launch{suffix}"
    path.write_text(content, encoding="utf-8", newline="")
    return path


def choose_linux_emulator(which: Which | None = None) -> str | None:
    """Return the first available Linux terminal emulator."""
    which = which or shutil.which
    for name in LINUX_EMULATORS:
        if which(name):
            return name
    return None


def linux_emulator_command(
    emulator: str,
    cmd: Sequence[str],
    name: str,
    cwd: str | None = None,
) -> list[str]:
    """Build the invocation that opens *emulator* running *cmd*."""
    keep_open = f"{join_posix(cmd)}; exec $SHELL"
    cmd = list(cmd)

    if emulator == "wt":
        return windows_wt_command(cmd, name, cwd)
    if emulator == "gnome-terminal":
        argv = ["gnome-terminal", "--title", name]
        if cwd:
            argv.append(f"--working-directory={cwd}")
        return [*argv, "--", "bash", "-lc", keep_open]
    if emulator == "konsole":
        argv = ["konsole", "--title", name]
        if cwd:
            argv += ["--workdir", cwd]
        return [*argv, "-e", "bash", "-lc", keep_open]
    if emulator == "xfce4-terminal":
        argv = ["xfce4-terminal", "--title", name]
        if cwd:
            argv.append(f"--working-directory={cwd}")
        return [*argv, "-x", "bash", "-lc", keep_open]
    if emulator == "kitty":
        argv = ["kitty", "--title", name]
        if cwd:
            argv += ["--directory", cwd]
        return [*argv, "bash", "-lc", keep_open]
    if emulator == "alacritty":
        argv = ["alacritty", "--title", name]
        if cwd:
            argv += ["--working-directory", cwd]
        return [*argv, "-e", "bash", "-lc", keep_open]
    # xterm and any other unknown emulator fall back to xterm-style flags.
    argv = [emulator, "-T", name]
    if cwd:
        argv += ["-e", "bash", "-lc", f"cd {quote_posix(cwd)} && {keep_open}"]
        return argv
    return [*argv, "-e", "bash", "-lc", keep_open]


def macos_osascript_command(cmd: Sequence[str], cwd: str | None = None) -> list[str]:
    """Open Terminal.app via AppleScript running *cmd*."""
    script = join_posix(cmd)
    if cwd:
        script = f"cd {quote_posix(cwd)} && {script}"
    return [
        "osascript",
        "-e",
        f'tell application "Terminal" to do script "{quote_applescript(script)}"',
        "-e",
        'tell application "Terminal" to activate',
    ]


# gnome-terminal exports the owning server's *unique* D-Bus name to child
# shells. When we spawn another gnome-terminal from inside one, its client
# pings that name and, if the old server has exited, prints
# "Failed to use specified server ... Falling back to default server". We
# always want the default server, so drop the stale pointers from the child.
_STALE_TERMINAL_ENV: tuple[str, ...] = (
    "GNOME_TERMINAL_SERVICE",
    "GNOME_TERMINAL_SCREEN",
)


def child_env() -> dict[str, str]:
    """Return the environment for a spawned terminal without stale pointers."""
    env = os.environ.copy()
    for name in _STALE_TERMINAL_ENV:
        env.pop(name, None)
    return env


# -- backend --------------------------------------------------------------
class TerminalBackend:
    name = "terminal"

    def __init__(
        self,
        which: Which | None = None,
        popen: Callable[..., subprocess.Popen[Any]] | None = None,
    ) -> None:
        self._which = which or shutil.which
        self._popen = popen or subprocess.Popen

    def _invocation(self, cmd: list[str], agent: Agent, platform: str) -> list[str]:
        cwd = agent.cwd
        if platform.startswith("win"):
            # Never pass the raw agent command to `wt`: it treats `;` as a
            # command separator, which splits a system prompt into several
            # bogus commands (one window each). Render a .cmd script instead
            # and let cmd.exe run it, where the prompt is just quoted text.
            script = write_temp_script(build_windows_script(cmd, cwd), suffix=".cmd")
            if self._which("wt"):
                return windows_wt_command(
                    ["cmd", "/k", str(script)],
                    agent.name or agent.role,
                    cwd,
                )
            return windows_start_command(script)
        if platform == "darwin":
            return macos_osascript_command(cmd, cwd)
        if os.environ.get("TMUX"):
            argv = ["tmux", "new-window", "-n", agent.name or agent.role]
            if cwd:
                argv += ["-c", cwd]
            return argv + list(cmd)
        emulator = choose_linux_emulator(self._which)
        if emulator is None:
            raise LaunchError(
                "no supported terminal emulator found (tried: "
                + ", ".join(LINUX_EMULATORS)
                + ")"
            )
        return linux_emulator_command(emulator, cmd, agent.name or agent.role, cwd)

    def launch(
        self, agents: list[Agent], options: LaunchOptions, run_id: str
    ) -> LaunchResult:
        platform = options.platform or sys.platform
        env = child_env()
        commands: list[list[str]] = []
        pids: list[int | None] = []
        for agent in agents:
            cmd = agent.build_argv()
            commands.append(cmd)
            invocation = self._invocation(cmd, agent, platform)
            try:
                process = self._popen(invocation, cwd=agent.cwd or None, env=env)
            except OSError as error:
                raise LaunchError(
                    f"failed to launch agent {agent.role!r}: {error}"
                ) from error
            pids.append(getattr(process, "pid", None))
        return LaunchResult(
            run_id=run_id,
            backend=self.name,
            commands=commands,
            agents=list(agents),
            pids=pids,
        )
