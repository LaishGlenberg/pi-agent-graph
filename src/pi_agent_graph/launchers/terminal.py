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


def keep_open_command(cmd: Sequence[str]) -> str:
    """Render *cmd* as a POSIX shell string that then keeps a shell open."""
    return f"{join_posix(cmd)}; exec $SHELL"


LINUX_EMULATORS: tuple[str, ...] = (
    "wt",
    "gnome-terminal",
    "konsole",
    "xfce4-terminal",
    "kitty",
    "alacritty",
    "xterm",
)

#: tmux server socket for single-window layouts. A dedicated server keeps a
#: multiplexed run out of the user's default tmux session.
MULTIPLEXER_SOCKET = "pi-agent-graph"

#: Layouts that multiplex every agent into one terminal window (Linux only).
MULTIPLEXED_LAYOUTS: tuple[str, ...] = ("tab", "split")

#: Pane layouts that need a ``client-resized`` hook to stay balanced. tmux
#: applies a named layout once; after that an incremental window resize hands
#: all the new space to the first pane and pins the rest. Re-applying the
#: layout on each resize keeps these layouts even. The ``main-*`` layouts are
#: deliberately excluded: re-applying them snaps the main pane back to tmux's
#: ``main-pane-height``/``main-pane-width`` instead of scaling with the window.
RESIZE_HOOK_LAYOUTS: tuple[str, ...] = (
    "tiled",
    "even-horizontal",
    "even-vertical",
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
    keep_open = keep_open_command(cmd)
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


# -- tmux multiplexing (single-window layouts) ---------------------------
def _tmux_argv(socket: str | None) -> list[str]:
    """Base tmux argv, pinned to a dedicated server when *socket* is set."""
    return ["tmux", "-L", socket] if socket else ["tmux"]


def tmux_new_session(
    session: str,
    name: str,
    cmd: Sequence[str],
    cwd: str | None = None,
    *,
    socket: str | None = None,
) -> list[str]:
    """Detached tmux session whose first window runs *cmd*."""
    argv = [*_tmux_argv(socket), "new-session", "-d", "-s", session, "-n", name]
    if cwd:
        argv += ["-c", cwd]
    return [*argv, keep_open_command(cmd)]


def tmux_new_window(
    session: str | None,
    name: str,
    cmd: Sequence[str],
    cwd: str | None = None,
    *,
    socket: str | None = None,
) -> list[str]:
    """New tmux window (a tab) running *cmd*."""
    argv = [*_tmux_argv(socket), "new-window"]
    if session:
        argv += ["-t", session]
    argv += ["-n", name]
    if cwd:
        argv += ["-c", cwd]
    return [*argv, keep_open_command(cmd)]


def tmux_split_window(
    session: str | None,
    cmd: Sequence[str],
    cwd: str | None = None,
    *,
    socket: str | None = None,
) -> list[str]:
    """Horizontal tmux split (side-by-side pane) running *cmd*."""
    argv = [*_tmux_argv(socket), "split-window", "-h"]
    if session:
        argv += ["-t", session]
    if cwd:
        argv += ["-c", cwd]
    return [*argv, keep_open_command(cmd)]


def tmux_select_pane(
    session: str | None, title: str, *, socket: str | None = None
) -> list[str]:
    """Title the active pane (run immediately after a split)."""
    argv = [*_tmux_argv(socket), "select-pane"]
    if session:
        argv += ["-t", session]
    return [*argv, "-T", title]


def tmux_select_layout(
    session: str | None, layout: str = "tiled", *, socket: str | None = None
) -> list[str]:
    """Rearrange the target window's panes into *layout*."""
    argv = [*_tmux_argv(socket), "select-layout"]
    if session:
        argv += ["-t", session]
    return [*argv, layout]


def tmux_attach(session: str, *, socket: str | None = None) -> list[str]:
    """Attach command run by the single terminal window."""
    return [*_tmux_argv(socket), "attach-session", "-t", session]


def tmux_destroy_unattached_hook(
    session: str, *, socket: str | None = None
) -> list[str]:
    """Session hook that tears the session down when its client detaches.

    ``destroy-unattached`` cannot simply be set before the first attach: tmux
    destroys a session immediately while the option is on and no client is
    attached, so the freshly created detached session would never attach.
    Enabling it from ``client-attached`` keeps the detached launch alive until
    the terminal window attaches, then closing that window (a client detach)
    kills the session, its panes, and the agents inside them.
    """
    return [
        *_tmux_argv(socket),
        "set-hook",
        "-t",
        session,
        "client-attached",
        f"set-option -t {session} destroy-unattached on",
    ]


def tmux_resize_hook(
    session: str, layout: str, *, socket: str | None = None
) -> list[str]:
    """Session-scoped hook re-applying *layout* whenever the client resizes.

    Scoped to *session* so it never touches other sessions sharing the server.
    See :data:`RESIZE_HOOK_LAYOUTS` for why only some layouts need it.
    """
    return [
        *_tmux_argv(socket),
        "set-hook",
        "-t",
        session,
        "client-resized",
        f"select-layout {layout}",
    ]


def _render_script(lines: Sequence[str]) -> str:
    return "\n".join(["#!/usr/bin/env bash", *lines]) + "\n"


def _check_layout(layout: str) -> None:
    if layout not in MULTIPLEXED_LAYOUTS:
        raise ValueError(f"not a multiplexed layout: {layout!r}")


def _layout_lines(
    entries: Sequence[tuple[str, Sequence[str], str | None]],
    *,
    session: str | None,
    layout: str,
    pane_layout: str,
    socket: str | None,
) -> list[str]:
    lines: list[str] = []
    for name, cmd, cwd in entries:
        if layout == "tab":
            lines.append(
                join_posix(tmux_new_window(session, name, cmd, cwd, socket=socket))
            )
        else:
            lines.append(
                join_posix(tmux_split_window(session, cmd, cwd, socket=socket))
            )
            lines.append(join_posix(tmux_select_pane(session, name, socket=socket)))
    if layout == "split":
        lines.append(
            join_posix(tmux_select_layout(session, pane_layout, socket=socket))
        )
    return lines


def tmux_session_script(
    entries: Sequence[tuple[str, Sequence[str], str | None]],
    *,
    session: str,
    layout: str,
    pane_layout: str = "tiled",
    socket: str | None = MULTIPLEXER_SOCKET,
) -> str:
    """Script that builds a detached tmux *session*, then attaches to it.

    *entries* is ``(name, cmd, cwd)`` per agent. ``layout='tab'`` gives each
    agent its own window; ``layout='split'`` tiles them as panes using the
    named tmux *pane_layout* (``tiled``, ``even-horizontal``, ...). The caller
    runs this in a single terminal window, so every agent shares one window.
    """
    _check_layout(layout)
    if not entries:
        raise ValueError("tmux_session_script needs at least one entry")
    name, cmd, cwd = entries[0]
    lines = [
        join_posix(tmux_new_session(session, name, cmd, cwd, socket=socket)),
        join_posix(tmux_destroy_unattached_hook(session, socket=socket)),
    ]
    lines += _layout_lines(
        entries[1:],
        session=session,
        layout=layout,
        pane_layout=pane_layout,
        socket=socket,
    )
    if layout == "split" and pane_layout in RESIZE_HOOK_LAYOUTS:
        lines.append(join_posix(tmux_resize_hook(session, pane_layout, socket=socket)))
    lines.append(join_posix(tmux_attach(session, socket=socket)))
    return _render_script(lines)


def tmux_current_script(
    entries: Sequence[tuple[str, Sequence[str], str | None]],
    *,
    layout: str,
    pane_layout: str = "tiled",
) -> str:
    """Script that adds tabs/panes to the tmux session we are already inside.

    Unlike :func:`tmux_session_script` this installs no resize hook: it runs in
    the user's own session, where a session hook would outlive the run.
    """
    _check_layout(layout)
    if not entries:
        raise ValueError("tmux_current_script needs at least one entry")
    return _render_script(
        _layout_lines(
            entries,
            session=None,
            layout=layout,
            pane_layout=pane_layout,
            socket=None,
        )
    )


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
        commands = [agent.build_argv() for agent in agents]
        if options.layout != "window" and platform.startswith("linux"):
            return self._launch_multiplexed(agents, commands, options, run_id, env)
        pids: list[int | None] = []
        for agent, cmd in zip(agents, commands):
            invocation = self._invocation(cmd, agent, platform)
            pids.append(
                self._spawn(invocation, cwd=agent.cwd or None, env=env, role=agent.role)
            )
        return LaunchResult(
            run_id=run_id,
            backend=self.name,
            commands=commands,
            agents=list(agents),
            pids=pids,
        )

    def _spawn(
        self,
        invocation: list[str],
        *,
        cwd: str | None,
        env: dict[str, str],
        role: str | None = None,
    ) -> int | None:
        try:
            process = self._popen(invocation, cwd=cwd, env=env)
        except OSError as error:
            if role is not None:
                raise LaunchError(
                    f"failed to launch agent {role!r}: {error}"
                ) from error
            raise LaunchError(f"failed to launch terminal: {error}") from error
        return getattr(process, "pid", None)

    def _launch_multiplexed(
        self,
        agents: list[Agent],
        commands: list[list[str]],
        options: LaunchOptions,
        run_id: str,
        env: dict[str, str],
    ) -> LaunchResult:
        """Open one terminal window holding a tmux tab/pane per agent."""
        layout = options.layout
        # ``tab`` adds tmux windows; every other multiplexed value (``split``
        # and the tmux layout names) tiles panes, with the layout name itself
        # arranging them. ``split`` is the plain ``tiled`` alias.
        mode = "tab" if layout == "tab" else "split"
        pane_layout = "tiled" if layout in ("tab", "split") else layout
        entries = [
            (agent.name or agent.role, cmd, agent.cwd)
            for agent, cmd in zip(agents, commands)
        ]
        if os.environ.get("TMUX"):
            # Already inside tmux: add windows/panes to the current session.
            script = write_temp_script(
                tmux_current_script(entries, layout=mode, pane_layout=pane_layout),
                suffix=".sh",
            )
            pid = self._spawn(["bash", str(script)], cwd=None, env=env)
        else:
            if not self._which("tmux"):
                raise LaunchError(
                    f"layout {layout!r} requires tmux on PATH "
                    "(install tmux, or use layout='window')"
                )
            script = write_temp_script(
                tmux_session_script(
                    entries,
                    session=run_id,
                    layout=mode,
                    pane_layout=pane_layout,
                ),
                suffix=".sh",
            )
            emulator = choose_linux_emulator(self._which)
            if emulator is None:
                raise LaunchError(
                    "no supported terminal emulator found (tried: "
                    + ", ".join(LINUX_EMULATORS)
                    + ")"
                )
            invocation = linux_emulator_command(emulator, ["bash", str(script)], run_id)
            pid = self._spawn(invocation, cwd=None, env=env)
        # One window was opened for the whole roster; only the first agent can
        # carry a pid, the rest run inside the same process tree.
        return LaunchResult(
            run_id=run_id,
            backend=self.name,
            commands=commands,
            agents=list(agents),
            pids=[pid, *([None] * (len(agents) - 1))],
        )
