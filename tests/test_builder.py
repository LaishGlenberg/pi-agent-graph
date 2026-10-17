"""Tests for the AgentGraphBuilder."""

from __future__ import annotations

from pathlib import Path

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


# -- resource defaults -----------------------------------------------------
def make_agent_dir(tmp_path: Path, *names: str) -> Path:
    agent_dir = tmp_path / "agent"
    for name in names:
        extension = agent_dir / "extensions" / name
        extension.mkdir(parents=True)
        (extension / "index.ts").write_text("", encoding="utf-8")
    return agent_dir


def test_builder_extensions_apply_to_scenario_agents(tmp_path):
    agent_dir = make_agent_dir(tmp_path, "ext")
    builder = AgentGraphBuilder()
    builder.set_extensions("ext", agent_dir=agent_dir)

    agents = builder.get_scenario("checklist_iteration").get_agents()

    resolved = str((agent_dir / "extensions" / "ext").resolve())
    for agent in agents:
        argv = agent.build_argv()
        assert argv[:2] == ["pi", "-ne"]
        assert argv[argv.index("--extension") + 1] == resolved


def test_builder_skills_apply_to_scenario_agents(tmp_path):
    agent_dir = tmp_path / "agent"
    skill = agent_dir / "skills" / "review.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("", encoding="utf-8")
    builder = AgentGraphBuilder()
    builder.set_skills("review", agent_dir=agent_dir)

    planner, worker = builder.get_scenario("checklist_iteration").get_agents()

    for agent in (planner, worker):
        assert "-ns" in agent.build_argv()
        assert str(skill.resolve()) in agent.build_argv()


def test_builder_tools_apply_to_scenario_agents():
    builder = AgentGraphBuilder()
    builder.set_tools("read", "bash")

    planner, worker = builder.get_scenario("checklist_iteration").get_agents()

    for agent in (planner, worker):
        assert "--exclude-tools" in agent.build_argv()


def test_builder_context_off_applies_to_scenario_agents():
    builder = AgentGraphBuilder()
    builder.use_context.set(False)

    planner, worker = builder.get_scenario("checklist_iteration").get_agents()

    assert "-nc" in planner.build_argv()
    assert "-nc" in worker.build_argv()


def test_per_agent_resources_beat_builder_defaults(tmp_path):
    agent_dir = make_agent_dir(tmp_path, "global", "own")
    builder = AgentGraphBuilder()
    builder.set_extensions("global", agent_dir=agent_dir)

    planner, worker = builder.get_scenario("checklist_iteration").get_agents()
    planner.set_extensions("own", agent_dir=agent_dir)

    planner_argv = planner.build_argv()
    worker_argv = worker.build_argv()
    assert str((agent_dir / "extensions" / "own").resolve()) in planner_argv
    assert str((agent_dir / "extensions" / "global").resolve()) not in planner_argv
    assert str((agent_dir / "extensions" / "global").resolve()) in worker_argv


def test_per_agent_tools_beat_builder_defaults():
    builder = AgentGraphBuilder()
    builder.set_tools("read", "bash")

    planner, worker = builder.get_scenario("checklist_iteration").get_agents()
    planner.set_tools("read")

    planner_argv = planner.build_argv()
    worker_argv = worker.build_argv()
    planner_excluded = planner_argv[planner_argv.index("--exclude-tools") + 1]
    worker_excluded = worker_argv[worker_argv.index("--exclude-tools") + 1]
    assert "bash" in planner_excluded
    assert "bash" not in worker_excluded


def test_builder_empty_extensions_disables_for_every_agent():
    builder = AgentGraphBuilder()
    builder.set_extensions()

    planner, worker = builder.get_scenario("checklist_iteration").get_agents()

    for agent in (planner, worker):
        argv = agent.build_argv()
        assert "-ne" in argv
        assert "--extension" not in argv


def test_builder_extensions_replace_saved_config_extensions(tmp_path):
    agent_dir = make_agent_dir(tmp_path, "own")

    class FakeLoader:
        def get(self, name):
            return ["pi", "-ne", "--extension", "/config-ext"]

    role = Role(name="worker", description="d", config="w1")
    scenario = Scenario(key="k", description="desc", roles={"worker": role})
    builder = AgentGraphBuilder(loader=FakeLoader())
    builder.set_extensions("own", agent_dir=agent_dir)

    agent = ScenarioBuilder(builder, scenario).get("worker")
    argv = agent.build_argv()

    assert "/config-ext" not in argv
    assert str((agent_dir / "extensions" / "own").resolve()) in argv
