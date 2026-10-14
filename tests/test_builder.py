"""Tests for the AgentGraphBuilder."""

from __future__ import annotations

import pytest

from pi_agent_graph.builder import (
    AgentGraphBuilder,
    ScenarioBuilder,
    render_system_prompt,
)
from pi_agent_graph.errors import ScenarioNotFoundError
from pi_agent_graph.models import Role, Scenario


def test_shared_context_and_goal():
    builder = AgentGraphBuilder()
    builder.set_shared_goal("G")
    builder.set_shared_context("C")
    assert builder.shared_goal == "G"
    assert builder.shared_context == "C"


def test_list_scenarios():
    assert set(AgentGraphBuilder().list_scenarios()) == {
        "checklist_iteration",
        "subagent_scouting",
        "scout_worker_planner",
    }


def test_get_agents_renders_prompts():
    builder = AgentGraphBuilder()
    builder.set_shared_goal("Build a site")
    builder.set_shared_context("Use intercom")
    agents = builder.get_scenario("checklist_iteration").get_agents()
    assert [a.role for a in agents] == ["planner", "worker"]
    planner = agents[0]
    assert "Build a site" in planner.system_prompt
    assert "Use intercom" in planner.system_prompt
    assert "planner" in planner.system_prompt
    assert planner.name == "planner"


def test_get_agents_returns_fresh_agents():
    builder = AgentGraphBuilder()
    scenario = builder.get_scenario("subagent_scouting")
    assert scenario.get_agents() is not scenario.get_agents()


def test_get_single_role():
    builder = AgentGraphBuilder()
    worker = builder.get_scenario("subagent_scouting").get("worker")
    assert worker.role == "worker"


def test_get_unknown_role_raises_keyerror():
    builder = AgentGraphBuilder()
    with pytest.raises(KeyError):
        builder.get_scenario("subagent_scouting").get("nope")


def test_unknown_scenario_raises():
    with pytest.raises(ScenarioNotFoundError):
        AgentGraphBuilder().get_scenario("nope")


def test_render_system_prompt_function():
    role = Role(name="scout", description="fetch things")
    text = render_system_prompt(role, "scenario desc", "the goal", "the context")
    for needle in ["scout", "fetch things", "scenario desc", "the goal", "the context"]:
        assert needle in text


def test_render_system_prompt_builder_method():
    builder = AgentGraphBuilder()
    builder.set_shared_goal("G")
    role = Role(name="worker", description="D")
    assert "G" in builder.render_system_prompt(role, "S")


def test_get_agent_loader_caches_default():
    builder = AgentGraphBuilder()
    assert builder.get_agent_loader() is builder.get_agent_loader()


def test_get_agent_loader_with_explicit_path(tmp_path):
    builder = AgentGraphBuilder()
    path = tmp_path / "config.json"
    loader = builder.get_agent_loader(path=str(path))
    assert str(loader.config_path) == str(path)


def test_get_agent_loader_does_not_cache_explicit_path():
    builder = AgentGraphBuilder()
    first = builder.get_agent_loader(path="/a/config.json")
    second = builder.get_agent_loader(path="/b/config.json")
    assert first is not second


def test_scenario_get_agents_autoloads_role_config():
    class FakeLoader:
        def get(self, name):
            return ["pi", "--from", name]

    role = Role(name="worker", description="d", config="w1")
    scenario = Scenario(key="k", description="desc", roles={"worker": role})
    builder = AgentGraphBuilder(loader=FakeLoader())
    agent = ScenarioBuilder(builder, scenario).get("worker")
    assert agent.base_argv == ["pi", "--from", "w1"]
    assert agent.system_prompt


def test_start_with_print_backend():
    builder = AgentGraphBuilder()
    agents = builder.get_scenario("checklist_iteration").get_agents()
    for agent in agents:
        agent.set_command(["pi", "-ne"])
    result = builder.start(agents, backend="print")
    assert result.backend == "print"
    assert len(result.commands) == 2


def test_start_dry_prints_without_launching(capsys):
    builder = AgentGraphBuilder()
    agents = builder.get_scenario("checklist_iteration").get_agents()
    for agent in agents:
        agent.set_command(["pi", "-ne"])
    result = builder.start_dry(agents)
    out = capsys.readouterr().out
    assert result.backend == "print"
    assert result.pids == [None, None]
    assert "worker" in out
    assert "planner" in out


def test_start_dry_orders_initiator_last(capsys):
    builder = AgentGraphBuilder()
    planner, worker = builder.get_scenario("checklist_iteration").get_agents()
    planner.set_command(["pi", "-ne"])
    worker.set_command(["pi", "-ne"])
    planner.set_prompt("go")
    result = builder.start_dry([planner, worker])
    assert [agent.role for agent in result.agents] == ["worker", "planner"]


def test_save_bash(tmp_path):
    builder = AgentGraphBuilder()
    agents = builder.get_scenario("subagent_scouting").get_agents()
    for agent in agents:
        agent.set_command(["pi", "-ne"])
    out = tmp_path / "flow.sh"
    path = builder.save_bash(agents, str(out))
    assert path == str(out)
    assert out.exists()


def test_start_applies_cwd_to_agents(tmp_path):
    builder = AgentGraphBuilder()
    planner, worker = builder.get_scenario("checklist_iteration").get_agents()
    for agent in (planner, worker):
        agent.set_command(["pi", "-ne"])
    builder.start([planner, worker], backend="print", cwd=str(tmp_path))
    assert planner.cwd == str(tmp_path)
    assert worker.cwd == str(tmp_path)


def test_start_cwd_does_not_override_existing_agent_cwd(tmp_path):
    builder = AgentGraphBuilder()
    planner, worker = builder.get_scenario("checklist_iteration").get_agents()
    for agent in (planner, worker):
        agent.set_command(["pi", "-ne"])
    planner.set_dir("/keep")
    builder.start([planner, worker], backend="print", cwd=str(tmp_path))
    assert planner.cwd == "/keep"
    assert worker.cwd == str(tmp_path)


def test_start_dry_applies_cwd(tmp_path):
    builder = AgentGraphBuilder()
    agents = builder.get_scenario("subagent_scouting").get_agents()
    for agent in agents:
        agent.set_command(["pi", "-ne"])
    result = builder.start_dry(agents, cwd=str(tmp_path))
    assert all(agent.cwd == str(tmp_path) for agent in result.agents)


def test_save_bash_applies_cwd(tmp_path):
    builder = AgentGraphBuilder()
    agents = builder.get_scenario("subagent_scouting").get_agents()
    for agent in agents:
        agent.set_command(["pi", "-ne"])
    builder.save_bash(agents, str(tmp_path / "flow.sh"), cwd=str(tmp_path))
    assert all(agent.cwd == str(tmp_path) for agent in agents)
