"""Tests for the print backend (dry-run preview)."""

from __future__ import annotations

from pi_agent_graph.launchers import LaunchOptions, launch
from pi_agent_graph.models import Agent


def make(role: str, prompt: str | None = None, argv=("pi", "-ne")) -> Agent:
    agent = Agent(role=role, prompt=prompt)
    agent.set_command(list(argv))
    return agent


def test_print_backend_returns_result(capsys):
    worker = make("worker")
    planner = make("planner", "go")
    result = launch(
        [planner, worker],
        backend="print",
        options=LaunchOptions(run_id="rid", platform="linux"),
    )
    assert result.backend == "print"
    assert result.run_id == "rid"
    assert result.pids == [None, None]
    assert [agent.role for agent in result.agents] == ["worker", "planner"]


def test_print_renders_posix_script(capsys):
    launch(
        [make("worker")],
        backend="print",
        options=LaunchOptions(run_id="r", platform="linux"),
    )
    out = capsys.readouterr().out
    assert out.startswith("#!/usr/bin/env bash")
    assert "# run_id: r" in out
    assert "# agents: worker" in out


def test_print_renders_windows_script(capsys):
    launch(
        [make("worker")],
        backend="print",
        options=LaunchOptions(run_id="r", platform="win32"),
    )
    out = capsys.readouterr().out
    assert out.startswith("@echo off")
    assert 'start ""' in out


def test_print_output_is_identical_to_saved_script(capsys, tmp_path):
    options = {"run_id": "r", "platform": "linux"}
    launch([make("worker")], backend="print", options=LaunchOptions(**options))
    printed = capsys.readouterr().out

    out = tmp_path / "run.sh"
    launch(
        [make("worker")],
        backend="bash",
        options=LaunchOptions(bash_path=str(out), **options),
    )
    assert out.read_text(encoding="utf-8") == printed


def test_print_orders_initiator_last(capsys):
    planner = make("planner", "go")
    worker = make("worker")
    result = launch(
        [planner, worker],
        backend="print",
        options=LaunchOptions(run_id="r", platform="linux"),
    )
    assert [agent.role for agent in result.agents] == ["worker", "planner"]
    assert "# agents: worker, planner" in capsys.readouterr().out


def test_print_uses_options_backend_when_not_given(capsys):
    result = launch(
        [make("worker")],
        options=LaunchOptions(backend="print", run_id="r", platform="linux"),
    )
    assert result.backend == "print"
