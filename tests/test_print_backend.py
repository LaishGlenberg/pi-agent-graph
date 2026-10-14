"""Tests for the print backend."""

from __future__ import annotations

import shlex

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
        [planner, worker], backend="print", options=LaunchOptions(run_id="rid")
    )
    assert result.backend == "print"
    assert result.run_id == "rid"
    assert result.pids == [None, None]
    assert [a.role for a in result.agents] == ["worker", "planner"]


def test_print_backend_prints_one_line_per_agent(capsys):
    launch(
        [make("worker"), make("planner", "go")],
        backend="print",
        options=LaunchOptions(run_id="rid"),
    )
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert "worker" in lines[0]
    assert "planner" in lines[1]


def test_print_output_round_trips(capsys):
    agent = make("worker", "multi\nline 'x' $y")
    launch([agent], backend="print", options=LaunchOptions(run_id="r"))
    line = capsys.readouterr().out.strip()
    assert shlex.split(line, posix=True) == agent.build_argv()


def test_print_uses_options_backend_when_not_given(capsys):
    result = launch(
        [make("worker")], options=LaunchOptions(backend="print", run_id="r")
    )
    assert result.backend == "print"
