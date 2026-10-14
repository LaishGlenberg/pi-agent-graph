"""Tests for the terminal backend and its pure invocation helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from pi_agent_graph.errors import LaunchError
from pi_agent_graph.launchers.terminal import (
    LINUX_EMULATORS,
    TerminalBackend,
    build_windows_script,
    choose_linux_emulator,
    linux_emulator_command,
    macos_osascript_command,
    normalize_windows_args,
    windows_start_command,
    windows_wt_command,
)
from pi_agent_graph.launchers.types import LaunchOptions
from pi_agent_graph.models import Agent


def which_only(target: str):
    return lambda name: f"/usr/bin/{name}" if name == target else None


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


def test_backend_launch_wraps_oserror():
    def boom(*args, **kwargs):
        raise OSError("nope")

    backend = TerminalBackend(which=which_only("xterm"), popen=boom)
    with pytest.raises(LaunchError):
        backend.launch([make()], LaunchOptions(run_id="r", platform="linux"), "r")
