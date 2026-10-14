"""Tests for the public API surface."""

from __future__ import annotations

import pi_agent_graph as pag


def test_version_is_string():
    assert isinstance(pag.__version__, str)
    assert pag.__version__


def test_main_prints_help(capsys):
    assert pag.main([]) == 0
    output = capsys.readouterr().out
    assert "pi-agent-graph" in output


def test_exports_present():
    for name in [
        "Agent",
        "AgentGraphBuilder",
        "ConfigLoader",
        "LaunchOptions",
        "LaunchResult",
        "launch",
        "Role",
        "Scenario",
        "ScenarioBuilder",
        "SCENARIOS",
        "get_scenario",
        "scenario_names",
        "render_system_prompt",
        "parse_dry_run",
    ]:
        assert hasattr(pag, name), name


def test_error_hierarchy():
    for name in [
        "ConfigNotFoundError",
        "ConfigParseError",
        "PiCliNotFoundError",
        "SavedConfigNotFoundError",
        "ScenarioNotFoundError",
        "ValidationError",
        "LaunchError",
    ]:
        error = getattr(pag, name)
        assert issubclass(error, pag.PiAgentGraphError)


def test_readme_quickstart_shapes():
    builder = pag.AgentGraphBuilder()
    builder.set_shared_goal("goal")
    builder.set_shared_context("context")
    planner, worker = builder.get_scenario("checklist_iteration").get_agents()
    planner.set_command(["pi", "-ne"])
    worker.set_command(["pi", "-ne"])
    planner.set_prompt("go")
    result = builder.start([planner, worker], backend="print")
    assert result.commands[0] == worker.build_argv()
    assert result.commands[1] == planner.build_argv()
