"""Tests for the top-level launch pipeline."""

from __future__ import annotations

import pytest

from pi_agent_graph.errors import ValidationError
from pi_agent_graph.launchers import LaunchOptions, launch, new_run_id
from pi_agent_graph.models import Agent


def make(role: str, prompt: str | None = None, argv=("pi", "-ne")) -> Agent:
    agent = Agent(role=role, prompt=prompt)
    agent.set_command(list(argv))
    return agent


def test_new_run_id_shape():
    run_id = new_run_id()
    assert "-" in run_id
    date, _, suffix = run_id.partition("-")
    assert len(date) == 8
    assert len(suffix) > 0


def test_launch_orders_initiator_last(capsys):
    planner = make("planner", "go")
    worker = make("worker")
    result = launch(
        [planner, worker], backend="print", options=LaunchOptions(run_id="r")
    )
    assert [a.role for a in result.agents] == ["worker", "planner"]


def test_launch_sets_run_scoped_session_dir(tmp_path):
    agent = make("worker")
    launch(
        [agent],
        backend="print",
        options=LaunchOptions(run_id="rid", session_dir=str(tmp_path)),
    )
    run_dir = tmp_path / "rid"
    assert run_dir.is_dir()
    assert agent.session_dir == str(run_dir)
    assert "--session-dir" in agent.build_argv()


def test_launch_does_not_override_existing_session_dir(tmp_path):
    agent = make("worker")
    agent.set_session_dir("/keep")
    launch(
        [agent],
        backend="print",
        options=LaunchOptions(run_id="rid", session_dir=str(tmp_path)),
    )
    assert agent.session_dir == "/keep"


def test_launch_sets_cwd(tmp_path):
    agent = make("worker")
    launch(
        [agent],
        backend="print",
        options=LaunchOptions(run_id="r", cwd=str(tmp_path)),
    )
    assert agent.cwd == str(tmp_path)


def test_launch_does_not_override_existing_cwd(tmp_path):
    agent = make("worker")
    agent.set_cwd("/keep")
    launch(
        [agent],
        backend="print",
        options=LaunchOptions(run_id="r", cwd=str(tmp_path)),
    )
    assert agent.cwd == "/keep"


def test_launch_unknown_backend_raises():
    with pytest.raises(ValidationError):
        launch([make("worker")], backend="wat")


def test_launch_empty_roster_raises():
    with pytest.raises(ValidationError):
        launch([], backend="print")


def test_launch_uses_options_backend():
    result = launch(
        [make("worker")], options=LaunchOptions(backend="print", run_id="r")
    )
    assert result.backend == "print"


def test_launch_explicit_backend_overrides_options():
    result = launch(
        [make("worker")],
        backend="print",
        options=LaunchOptions(backend="terminal", run_id="r"),
    )
    assert result.backend == "print"
