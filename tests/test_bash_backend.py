"""Tests for the bash backend."""

from __future__ import annotations

from pathlib import Path

from pi_agent_graph.launchers import LaunchOptions, launch
from pi_agent_graph.launchers.bash import render_bash_script
from pi_agent_graph.models import Agent


def which_only(target: str):
    return lambda name: f"/usr/bin/{name}" if name == target else None


def make(role: str, prompt: str | None = None, argv=("pi", "-ne")) -> Agent:
    agent = Agent(role=role, prompt=prompt)
    agent.set_command(list(argv))
    return agent


def test_bash_backend_writes_posix_file(tmp_path):
    out = tmp_path / "flows" / "run.sh"
    result = launch(
        [make("worker")],
        backend="bash",
        options=LaunchOptions(bash_path=str(out), run_id="rid", platform="linux"),
    )
    assert result.path == str(out)
    assert result.backend == "bash"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "run_id: rid" in text
    assert "agents: worker" in text


def test_bash_backend_creates_parent_dirs(tmp_path):
    out = tmp_path / "a" / "b" / "run.sh"
    launch(
        [make("worker")],
        backend="bash",
        options=LaunchOptions(bash_path=str(out), run_id="r", platform="linux"),
    )
    assert out.exists()


def test_bash_backend_windows(tmp_path):
    out = tmp_path / "run.cmd"
    launch(
        [make("worker")],
        backend="bash",
        options=LaunchOptions(bash_path=str(out), run_id="r", platform="win32"),
    )
    text = out.read_text(encoding="utf-8")
    assert text.startswith("@echo off")
    assert 'start ""' in text


def test_bash_windows_file_uses_crlf_without_doubling(tmp_path):
    out = tmp_path / "run.cmd"
    launch(
        [make("worker")],
        backend="bash",
        options=LaunchOptions(bash_path=str(out), run_id="r", platform="win32"),
    )
    raw = out.read_bytes()
    assert b"\r\n" in raw
    assert b"\r\r\n" not in raw


def test_bash_posix_file_keeps_lf(tmp_path):
    out = tmp_path / "run.sh"
    launch(
        [make("worker")],
        backend="bash",
        options=LaunchOptions(bash_path=str(out), run_id="r", platform="linux"),
    )
    raw = out.read_bytes()
    assert raw.startswith(b"#!")
    assert b"\r\n" not in raw


def test_bash_backend_records_commands(tmp_path):
    planner = make("planner", "go")
    result = launch(
        [planner],
        backend="bash",
        options=LaunchOptions(
            bash_path=str(tmp_path / "r.sh"), run_id="r", platform="linux"
        ),
    )
    assert result.commands == [planner.build_argv()]
    assert result.pids == [None]


def test_render_linux_falls_back_when_no_emulator():
    script = render_bash_script(
        [make("worker")], run_id="r", platform="linux", which=lambda name: None
    )
    assert " &" in script


def test_render_linux_uses_selected_emulator():
    script = render_bash_script(
        [make("worker")],
        run_id="r",
        platform="linux",
        which=which_only("gnome-terminal"),
    )
    assert "gnome-terminal" in script


def test_render_includes_cwd_and_names():
    script = render_bash_script(
        [make("worker")],
        run_id="r",
        platform="linux",
        cwd="/work",
        which=which_only("xterm"),
    )
    assert "cd '/work'" in script
    assert "# agents: worker" in script


def test_render_darwin_uses_osascript():
    script = render_bash_script(
        [make("worker")], run_id="r", platform="darwin", which=lambda name: None
    )
    assert "osascript" in script


def test_render_windows_uses_start():
    script = render_bash_script(
        [make("worker")], run_id="r", platform="win32"
    )
    assert 'start ""' in script
    assert "cd /d" not in script


def test_render_windows_includes_cwd():
    script = render_bash_script(
        [make("worker")], run_id="r", platform="win32", cwd="C:/work"
    )
    assert 'cd /d "C:/work"' in script


def test_render_windows_collapses_multiline_prompt():
    agent = make("worker", argv=("pi",))
    agent.set_system_prompt("line1\nline2\n\nline3")
    script = render_bash_script([agent], run_id="r", platform="win32")
    assert "line1 line2 line3" in script
    start_lines = [
        line
        for line in script.rstrip("\r\n").split("\r\n")
        if line.startswith('start ""')
    ]
    assert len(start_lines) == 1


def test_render_header_lists_all_agents():
    script = render_bash_script(
        [make("planner"), make("worker")],
        run_id="r",
        platform="linux",
        which=which_only("xterm"),
    )
    assert "# agents: planner, worker" in script


def test_render_returns_trailing_newline():
    script = render_bash_script(
        [make("worker")], run_id="r", platform="linux", which=lambda name: None
    )
    assert script.endswith("\n")
