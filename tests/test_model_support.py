"""Model selection and the dynamic prompt, exercised end to end via fakes.

The :class:`~fakes.FakePiCli` and :class:`~fakes.FakeLauncher` stand in for the
``pi-cli`` subprocess and the terminal backend, so the whole
config -> fixture -> agents -> launch pipeline runs without spawning anything.
"""

from __future__ import annotations

from fakes import FakeLauncher, FakePiCli

from pi_agent_graph.builder import AgentGraphBuilder
from pi_agent_graph.models import Agent


def make_agent(role: str, **kwargs) -> Agent:
    """A minimal agent with a valid command and no model unless given one."""
    agent = Agent(role=role, **kwargs)
    agent.set_command(["pi", "-ne"])
    return agent


# -- builder-level defaults ------------------------------------------------
def test_builder_model_applies_to_every_agent():
    builder = AgentGraphBuilder()
    builder.set_model("opencode-go/mimo-v2.5", "low")
    agents = builder.get_scenario("checklist_iteration").get_agents()
    assert [agent.model for agent in agents] == ["opencode-go/mimo-v2.5:low"] * 2
    for agent in agents:
        argv = agent.build_argv()
        assert argv[argv.index("--model") + 1] == "opencode-go/mimo-v2.5:low"


def test_per_agent_model_beats_builder_default():
    builder = AgentGraphBuilder()
    builder.set_model("global", "low")
    planner, worker = builder.get_scenario("checklist_iteration").get_agents()
    planner.set_model("opencode-go/mimo-v2.5-pro", "high")
    assert planner.model == "opencode-go/mimo-v2.5-pro:high"
    assert worker.model == "global:low"


def test_builder_default_fills_manually_built_agents(monkeypatch):
    launcher = FakeLauncher()
    launcher.install(monkeypatch)
    builder = AgentGraphBuilder()
    builder.set_model("python/global", "high")
    agent = make_agent("worker")
    builder.start([agent], backend="print")
    assert agent.model == "python/global:high"
    command = launcher.commands()[0]
    assert command[command.index("--model") + 1] == "python/global:high"


def test_builder_default_does_not_override_per_agent_model(monkeypatch):
    launcher = FakeLauncher()
    launcher.install(monkeypatch)
    builder = AgentGraphBuilder()
    builder.set_model("global")
    agent = make_agent("worker")
    agent.set_model("per-agent", "xhigh")
    builder.start([agent], backend="print")
    assert agent.model == "per-agent:xhigh"
    assert launcher.last.agents[0].model == "per-agent:xhigh"


def test_start_warns_on_default_model(monkeypatch, capsys):
    launcher = FakeLauncher()
    launcher.install(monkeypatch)
    builder = AgentGraphBuilder()
    agents = [make_agent("planner"), make_agent("worker")]
    builder.start(agents, backend="print")
    error = capsys.readouterr().err
    assert "default model" in error
    assert "[default_model]" in error
    assert "planner" in error


def test_start_dry_does_not_warn(monkeypatch, capsys):
    launcher = FakeLauncher()
    launcher.install(monkeypatch)
    builder = AgentGraphBuilder()
    builder.start_dry([make_agent("worker")])
    assert "default model" not in capsys.readouterr().err


def test_start_does_not_warn_when_model_set(monkeypatch, capsys):
    launcher = FakeLauncher()
    launcher.install(monkeypatch)
    builder = AgentGraphBuilder()
    builder.set_model("m", "low")
    builder.start([make_agent("worker")], backend="print")
    assert "default model" not in capsys.readouterr().err


# -- full pipeline ---------------------------------------------------------
def test_full_pipeline_overrides_config_model_and_prompt(tmp_path, monkeypatch):
    fake = FakePiCli(
        {
            "planner_cfg": [
                "pi",
                "-ne",
                "--name",
                "config-planner",
                "--model",
                "config/planner:low",
                "--system-prompt",
                "stale config prompt",
            ],
            "worker_cfg": ["pi", "-ne", "--model", "config/worker"],
        }
    )
    fake.install(monkeypatch)
    config = fake.write_config(tmp_path / "config.json")
    launcher = FakeLauncher()
    launcher.install(monkeypatch)

    seed = AgentGraphBuilder(loader=fake.loader(config))
    seed.save_fixture(
        "demo",
        "checklist_iteration",
        roles={"planner": "planner_cfg", "worker": "worker_cfg"},
        prompts={"planner": "go"},
        directory=tmp_path,
    )

    builder = AgentGraphBuilder(loader=fake.loader(config))
    builder.set_model("python/global", "high")
    scenario = builder.load_saved("demo", directory=tmp_path)
    builder.set_shared_goal("Ship it")
    planner, worker = scenario.get_agents()
    planner.set_model("python/planner", "xhigh")

    builder.start([planner, worker], backend="print", cwd=str(tmp_path))

    # Responders launch before the prompt-bearer.
    assert [agent.role for agent in launcher.last.agents] == ["worker", "planner"]
    commands = {
        agent.role: command
        for agent, command in zip(launcher.last.agents, launcher.commands())
    }

    planner_cmd = commands["planner"]
    assert planner_cmd[planner_cmd.index("--model") + 1] == "python/planner:xhigh"
    # Our rendered prompt replaces the config's saved one.
    assert planner_cmd.count("--system-prompt") == 1
    assert "stale config prompt" not in planner_cmd
    rendered = planner_cmd[planner_cmd.index("--system-prompt") + 1]
    assert "Ship it" in rendered
    assert planner_cmd[-2:] == ["--", "go"]

    worker_cmd = commands["worker"]
    assert worker_cmd[worker_cmd.index("--model") + 1] == "python/global:high"

    # Every saved command was resolved through the real loader.
    assert fake.requests
    assert all(env["PI_CLI_CONFIG"] == str(config) for _, env in fake.requests)


def test_fixture_config_model_respected_without_builder_default(tmp_path, monkeypatch):
    fake = FakePiCli({"worker_cfg": ["pi", "--model", "config/worker:low"]})
    fake.install(monkeypatch)
    config = fake.write_config(tmp_path / "config.json")

    builder = AgentGraphBuilder(loader=fake.loader(config))
    builder.save_fixture(
        "demo",
        "subagent_scouting",
        roles={"worker": "worker_cfg"},
        directory=tmp_path,
    )
    agents = (
        AgentGraphBuilder(loader=fake.loader(config))
        .load_saved("demo", directory=tmp_path)
        .get_agents()
    )
    worker = next(agent for agent in agents if agent.role == "worker")
    assert worker.model == "config/worker:low"
    assert worker.model_explicit is False
