"""Tests for the terminal backend and its pure invocation helpers."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import ClassVar

import pytest

from pi_agent_graph.errors import LaunchError
from pi_agent_graph.launchers.terminal import (
    LINUX_EMULATORS,
    MULTIPLEXER_SOCKET,
    TerminalBackend,
    build_windows_script,
    child_env,
    choose_linux_emulator,
    keep_open_command,
    linux_emulator_command,
    macos_osascript_command,
    normalize_windows_args,
    tmux_attach,
    tmux_current_script,
    tmux_new_session,
    tmux_new_window,
    tmux_select_layout,
    tmux_select_pane,
    tmux_session_script,
    tmux_split_window,
    windows_start_command,
    windows_wt_command,
)
from pi_agent_graph.launchers.types import LaunchOptions
from pi_agent_graph.models import Agent


def which_only(target: str):
    return lambda name: f"/usr/bin/{name}" if name == target else None


def which_many(*targets: str):
    return lambda name: f"/usr/bin/{name}" if name in targets else None


def make(
    role: str = "worker", cwd: str | None = None, prompt: str | None = None
) -> Agent:
    agent = Agent(role=role, cwd=cwd, prompt=prompt)
    agent.set_command(["pi", "-ne"])
    return agent


class FakeProcess:
    pid = 4242


class FakePopen:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.pid = 4242


# -- pure helpers ----------------------------------------------------------
def test_windows_wt_command():
    assert windows_wt_command(["pi", "-ne"], "worker", "C:/w") == [
        "wt",
        "-w",
        "0",
        "nt",
        "--title",
        "worker",
        "-d",
        "C:/w",
        "pi",
        "-ne",
    ]


def test_windows_wt_command_without_cwd():
    assert windows_wt_command(["pi"], "w") == [
        "wt",
        "-w",
        "0",
        "nt",
        "--title",
        "w",
        "pi",
    ]


def test_windows_wt_command_collapses_newlines():
    argv = windows_wt_command(
        ["pi", "--system-prompt", "line1\nline2\n\nline3"], "worker"
    )
    assert all("\n" not in token for token in argv)
    assert "line1 line2 line3" in argv


def test_windows_start_command():
    assert windows_start_command("C:/x/launch.cmd") == [
        "cmd",
        "/c",
        "start",
        "",
        "cmd",
        "/k",
        "C:/x/launch.cmd",
    ]


def test_build_windows_script_with_cwd():
    text = build_windows_script(["pi", "--system-prompt", "a b"], "C:/w")
    assert text.startswith("@echo off")
    assert 'cd /d "C:/w"' in text
    assert "pi" in text
    assert text.endswith("\r\n")


def test_build_windows_script_without_cwd():
    text = build_windows_script(["pi"], None)
    assert "cd /d" not in text


def test_normalize_windows_args_collapses_newlines():
    assert normalize_windows_args(["a\nb", "c\r\nd", "e"]) == ["a b", "c d", "e"]


def test_build_windows_script_keeps_multiline_prompt_on_one_line():
    text = build_windows_script(
        ["pi", "--system-prompt", "line1\nline2\n\nline3"], None
    )
    body = text.rstrip("\r\n")
    assert len(body.split("\r\n")) == 2  # header + one command line
    assert "line1 line2 line3" in text


def test_choose_linux_emulator_prefers_first_available():
    assert choose_linux_emulator(lambda name: "/bin/" + name) == LINUX_EMULATORS[0]


def test_choose_linux_emulator_specific():
    assert choose_linux_emulator(which_only("konsole")) == "konsole"


def test_choose_linux_emulator_none():
    assert choose_linux_emulator(lambda name: None) is None


@pytest.mark.parametrize(
    "emulator",
    ["gnome-terminal", "konsole", "xfce4-terminal", "kitty", "alacritty", "xterm"],
)
def test_linux_emulator_command_includes_title_cwd_and_keep_open(emulator):
    cmd = linux_emulator_command(emulator, ["pi", "-ne"], "worker", "/work")
    assert cmd[0] == emulator
    assert any("worker" in part for part in cmd)
    assert any("/work" in part for part in cmd)
    assert any("exec $SHELL" in part for part in cmd)


def test_linux_emulator_command_no_cwd():
    cmd = linux_emulator_command("xterm", ["pi"], "w")
    assert any("pi" in part for part in cmd)
    assert any("exec $SHELL" in part for part in cmd)


def test_linux_emulator_command_wt_is_delegated():
    cmd = linux_emulator_command("wt", ["pi"], "w", "C:/w")
    assert cmd[0] == "wt"


def test_macos_osascript_command():
    cmd = macos_osascript_command(["pi", "--system-prompt", 'a "b"'], "/work")
    assert cmd[0] == "osascript"
    assert any("Terminal" in part for part in cmd)
    assert any("cd " in part for part in cmd)
    assert any('\\"' in part for part in cmd)


# -- tmux multiplexing helpers --------------------------------------------
ENTRIES = [
    ("planner", ["pi", "-ne"], "/p"),
    ("worker", ["pi"], None),
]


def test_keep_open_command_appends_shell():
    assert keep_open_command(["pi", "-ne"]) == "'pi' '-ne'; exec $SHELL"


def test_tmux_new_session_includes_socket_session_and_cwd():
    cmd = tmux_new_session("run1", "planner", ["pi", "-ne"], "/work", socket="s")
    assert cmd[:5] == ["tmux", "-L", "s", "new-session", "-d"]
    assert "run1" in cmd and "planner" in cmd and "/work" in cmd
    assert cmd[-1].endswith("exec $SHELL")


def test_tmux_new_window_targets_session_and_titles_tab():
    cmd = tmux_new_window("run1", "worker", ["pi"], socket="s")
    assert cmd[:-1] == [
        "tmux",
        "-L",
        "s",
        "new-window",
        "-t",
        "run1",
        "-n",
        "worker",
    ]


def test_tmux_split_window_is_horizontal():
    cmd = tmux_split_window(None, ["pi"], "/w")
    assert cmd[:3] == ["tmux", "split-window", "-h"]
    assert "/w" in cmd
    assert cmd[-1].endswith("exec $SHELL")


def test_tmux_select_pane_titles_active_pane():
    assert tmux_select_pane(None, "worker") == [
        "tmux",
        "select-pane",
        "-T",
        "worker",
    ]


def test_tmux_select_layout_defaults_to_tiled():
    assert tmux_select_layout("run1", socket="s") == [
        "tmux",
        "-L",
        "s",
        "select-layout",
        "-t",
        "run1",
        "tiled",
    ]


def test_tmux_attach_command():
    assert tmux_attach("run1", socket="s") == [
        "tmux",
        "-L",
        "s",
        "attach-session",
        "-t",
        "run1",
    ]


def test_tmux_session_script_tab_uses_windows():
    script = tmux_session_script(ENTRIES, session="run1", layout="tab", socket=None)
    assert "new-session" in script
    assert script.count("new-window") == 1
    assert "split-window" not in script
    assert "attach-session" in script


def test_tmux_session_script_split_tiles_panes():
    script = tmux_session_script(ENTRIES, session="run1", layout="split", socket=None)
    assert "new-session" in script
    assert script.count("split-window") == 1
    assert script.count("select-pane") == 1
    assert "select-layout" in script and "tiled" in script
    assert "new-window" not in script
    assert "attach-session" in script


def test_tmux_session_script_uses_dedicated_server_by_default():
    script = tmux_session_script(ENTRIES, session="run1", layout="tab")
    assert MULTIPLEXER_SOCKET in script


def test_tmux_session_script_rejects_window_layout():
    with pytest.raises(ValueError):
        tmux_session_script(ENTRIES, session="run1", layout="window")


def test_tmux_current_script_has_no_session_or_attach():
    script = tmux_current_script(ENTRIES, layout="split")
    assert "new-session" not in script
    assert "attach-session" not in script
    assert "-L" not in script
    assert "split-window" in script


def test_tmux_script_quotes_prompts_safely():
    entries = [("p", ["pi", "--system-prompt", "a b; rm -rf /"], None)]
    script = tmux_session_script(entries, session="run1", layout="tab", socket=None)
    line = next(line for line in script.splitlines() if "new-session" in line)
    keep = shlex.split(line)[-1]
    inner = shlex.split(keep.removesuffix("; exec $SHELL"))
    assert inner == ["pi", "--system-prompt", "a b; rm -rf /"]


# -- backend invocation selection -----------------------------------------
def test_backend_windows_prefers_wt():
    backend = TerminalBackend(which=which_only("wt"), popen=FakePopen)
    invocation = backend._invocation(["pi"], make(), "win32")
    assert invocation[0] == "wt"


def test_backend_windows_wt_routes_through_generated_script():
    agent = make()
    agent.set_system_prompt("line1\nline2; line3")
    backend = TerminalBackend(which=which_only("wt"), popen=FakePopen)
    invocation = backend._invocation(agent.build_argv(), agent, "win32")
    assert invocation[:6] == ["wt", "-w", "0", "nt", "--title", "worker"]
    assert invocation[6:8] == ["cmd", "/k"]
    script = Path(invocation[8])
    assert script.suffix == ".cmd"
    assert script.exists()
    assert "line1 line2; line3" in script.read_text(encoding="utf-8")
    # The raw prompt (with its `;`) must never reach wt's command line.
    assert not any("line1" in token or ";" in token for token in invocation)


def test_backend_windows_falls_back_to_cmd_script():
    backend = TerminalBackend(which=lambda name: None, popen=FakePopen)
    invocation = backend._invocation(["pi"], make(), "win32")
    assert invocation[:4] == ["cmd", "/c", "start", ""]
    assert invocation[4:6] == ["cmd", "/k"]
    assert Path(invocation[6]).suffix == ".cmd"


def test_backend_linux_tmux(monkeypatch):
    monkeypatch.setenv("TMUX", "1")
    backend = TerminalBackend(which=lambda name: None, popen=FakePopen)
    invocation = backend._invocation(["pi"], make(cwd="/work"), "linux")
    assert invocation[:2] == ["tmux", "new-window"]
    assert "/work" in invocation


def test_backend_linux_uses_emulator():
    backend = TerminalBackend(which=which_only("xterm"), popen=FakePopen)
    invocation = backend._invocation(["pi"], make(), "linux")
    assert invocation[0] == "xterm"


def test_backend_linux_no_emulator_raises():
    backend = TerminalBackend(which=lambda name: None, popen=FakePopen)
    with pytest.raises(LaunchError):
        backend._invocation(["pi"], make(), "linux")


def test_backend_launch_returns_pids_and_commands():
    backend = TerminalBackend(which=which_only("xterm"), popen=FakePopen)
    result = backend.launch([make()], LaunchOptions(run_id="r", platform="linux"), "r")
    assert result.pids == [4242]
    assert result.commands == [["pi", "-ne", "--name", "worker"]]
    assert result.backend == "terminal"


def test_child_env_strips_stale_gnome_terminal_pointers(monkeypatch):
    monkeypatch.setenv("GNOME_TERMINAL_SERVICE", ":1.157")
    monkeypatch.setenv("GNOME_TERMINAL_SCREEN", "/org/gnome/Terminal/screen/x")
    env = child_env()
    assert "GNOME_TERMINAL_SERVICE" not in env
    assert "GNOME_TERMINAL_SCREEN" not in env
    assert env.get("PATH") == os.environ.get("PATH")


def test_backend_launch_passes_clean_env(monkeypatch):
    monkeypatch.setenv("GNOME_TERMINAL_SERVICE", ":1.157")
    monkeypatch.setenv("GNOME_TERMINAL_SCREEN", "/org/gnome/Terminal/screen/x")
    seen: dict[str, object] = {}

    class RecordingPopen(FakePopen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            seen.update(kwargs)

    backend = TerminalBackend(which=which_only("gnome-terminal"), popen=RecordingPopen)
    backend.launch([make()], LaunchOptions(run_id="r", platform="linux"), "r")
    env = seen["env"]
    assert isinstance(env, dict)
    assert "GNOME_TERMINAL_SERVICE" not in env
    assert "GNOME_TERMINAL_SCREEN" not in env


def test_backend_launch_wraps_oserror():
    def boom(*args, **kwargs):
        raise OSError("nope")

    backend = TerminalBackend(which=which_only("xterm"), popen=boom)
    with pytest.raises(LaunchError):
        backend.launch([make()], LaunchOptions(run_id="r", platform="linux"), "r")


class RecordingPopen(FakePopen):
    """FakePopen that records every invocation in ``calls``."""

    calls: ClassVar[list[list[str]]] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        RecordingPopen.calls.append(args[0])


def test_backend_default_layout_opens_window_per_agent(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    RecordingPopen.calls = []
    backend = TerminalBackend(which=which_only("xterm"), popen=RecordingPopen)
    result = backend.launch([make()], LaunchOptions(run_id="r", platform="linux"), "r")
    assert result.pids == [4242]
    assert RecordingPopen.calls[0][0] == "xterm"


def test_backend_layout_split_outside_tmux_opens_one_window(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    RecordingPopen.calls = []
    backend = TerminalBackend(which=which_many("xterm", "tmux"), popen=RecordingPopen)
    agents = [make("planner"), make("worker")]
    result = backend.launch(
        agents,
        LaunchOptions(run_id="r1", platform="linux", layout="split"),
        "r1",
    )
    assert len(RecordingPopen.calls) == 1
    assert RecordingPopen.calls[0][0] == "xterm"
    # The keep-open string runs a generated script that builds the session.
    script = Path(shlex.split(RecordingPopen.calls[0][-1])[1].rstrip(";"))
    text = script.read_text(encoding="utf-8")
    assert "split-window" in text
    assert "select-layout" in text
    assert "attach-session" in text
    assert "r1" in text
    assert result.commands == [a.build_argv() for a in agents]
    # Only the one window process can carry a pid; panes share its tree.
    assert result.pids == [4242, None]


def test_backend_layout_tab_outside_tmux_opens_one_window(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    RecordingPopen.calls = []
    backend = TerminalBackend(which=which_many("xterm", "tmux"), popen=RecordingPopen)
    backend.launch(
        [make("planner"), make("worker")],
        LaunchOptions(run_id="r1", platform="linux", layout="tab"),
        "r1",
    )
    assert len(RecordingPopen.calls) == 1
    text = Path(shlex.split(RecordingPopen.calls[0][-1])[1].rstrip(";")).read_text(
        encoding="utf-8"
    )
    assert "new-window" in text
    assert "split-window" not in text


def test_backend_layout_split_inside_tmux_targets_current_session(monkeypatch):
    monkeypatch.setenv("TMUX", "1")
    RecordingPopen.calls = []
    backend = TerminalBackend(which=lambda name: None, popen=RecordingPopen)
    result = backend.launch(
        [make("planner"), make("worker")],
        LaunchOptions(run_id="r1", platform="linux", layout="split"),
        "r1",
    )
    assert len(RecordingPopen.calls) == 1
    assert RecordingPopen.calls[0][0] == "bash"
    text = Path(RecordingPopen.calls[0][1]).read_text(encoding="utf-8")
    assert "split-window" in text
    assert "-L" not in text
    assert "new-session" not in text
    assert "attach-session" not in text
    assert result.pids == [4242, None]


def test_backend_layout_requires_tmux_outside_session(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    RecordingPopen.calls = []
    backend = TerminalBackend(which=which_only("xterm"), popen=RecordingPopen)
    with pytest.raises(LaunchError) as exc:
        backend.launch(
            [make()],
            LaunchOptions(run_id="r", platform="linux", layout="tab"),
            "r",
        )
    assert "tmux" in str(exc.value)
