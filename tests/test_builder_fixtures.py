"""Tests for builder fixture integration: save_fixture + load_saved."""

from __future__ import annotations

import pytest

from pi_agent_graph.builder import AgentGraphBuilder, ScenarioBuilder
from pi_agent_graph.errors import (
    FixtureFormatError,
    FixtureNotFoundError,
    ScenarioNotFoundError,
)
from pi_agent_graph.fixtures import RoleFixture, ScenarioFixture, save_fixture
from pi_agent_graph.models import Role, Scenario


class StubLoader:
    """Minimal stand-in for ConfigLoader: maps a name to a fixed argv."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self.mapping = mapping

    def get(self, name: str) -> list[str]:
        return self.mapping[name]


# -- save_fixture -> load_saved round trip --------------------------------
def test_save_and_load_round_trip(tmp_path):
    builder = AgentGraphBuilder()
    builder.set_shared_goal("Ship it")
    builder.set_shared_context("Use uv")
    path = builder.save_fixture(
        "demo",
        "checklist_iteration",
        roles={"planner": "planner_cfg", "worker": "worker_cfg"},
        prompts={"worker": "Do the thing"},
        names={"planner": "P1"},
        directory=tmp_path,
    )
    assert path == tmp_path / "demo.json"
    assert path.exists()

    loader = StubLoader(
        {
            "planner_cfg": ["pi", "--model", "fast"],
            "worker_cfg": ["pi", "--model", "thorough"],
        }
    )
    builder2 = AgentGraphBuilder(loader=loader)
    scenario_builder = builder2.load_saved("demo", directory=tmp_path)

    # Shared goal/context are backfilled onto the builder.
    assert builder2.shared_goal == "Ship it"
    assert builder2.shared_context == "Use uv"

    agents = scenario_builder.get_agents()
    by_role = {a.role: a for a in agents}

    planner = by_role["planner"]
    assert planner.name == "P1"
    assert planner.base_argv == ["pi"]
    assert planner.model == "fast"

    worker = by_role["worker"]
    assert worker.base_argv == ["pi"]
    assert worker.model == "thorough"
    assert worker.prompt == "Do the thing"
    # Prompt is rendered via build_argv's `--` path, not system_prompt.
    assert worker.system_prompt is not None
    assert worker.build_argv()[-2:] == ["--", "Do the thing"]


# -- fixture config overrides scenario config -----------------------------
def _custom_scenario_with_config() -> Scenario:
    return Scenario(
        key="custom",
        description="desc",
        roles={
            "lead": Role(name="lead", config="scenario_cfg"),
            "helper": Role(name="helper", config="scenario_cfg"),
        },
    )


def test_fixture_config_overrides_scenario_config():
    builder = AgentGraphBuilder(
        loader=StubLoader(
            {"scenario_cfg": ["pi", "scen"], "fixture_cfg": ["pi", "fixture"]}
        )
    )
    fixture = ScenarioFixture(
        identifier="x",
        scenario="custom",
        roles={"lead": RoleFixture(config="fixture_cfg")},
    )
    scenario_builder = ScenarioBuilder(
        builder, _custom_scenario_with_config(), fixture=fixture
    )
    by_role = {a.role: a for a in scenario_builder.get_agents()}
    # Fixture config wins for "lead".
    assert by_role["lead"].base_argv == ["pi", "fixture"]
    # "helper" has no fixture entry -> keeps scenario behavior.
    assert by_role["helper"].base_argv == ["pi", "scen"]


def test_fixture_without_config_keeps_scenario_behavior():
    builder = AgentGraphBuilder(loader=StubLoader({"scenario_cfg": ["pi", "scen"]}))
    fixture = ScenarioFixture(
        identifier="x",
        scenario="custom",
        roles={"lead": RoleFixture(prompt="Start here")},
    )
    scenario_builder = ScenarioBuilder(
        builder, _custom_scenario_with_config(), fixture=fixture
    )
    by_role = {a.role: a for a in scenario_builder.get_agents()}
    assert by_role["lead"].base_argv == ["pi", "scen"]
    assert by_role["lead"].prompt == "Start here"


# -- unknown role keys ----------------------------------------------------
def test_unknown_fixture_role_raises_from_get_agents():
    builder = AgentGraphBuilder()
    fixture = ScenarioFixture(
        identifier="x",
        scenario="custom",
        roles={"nope": RoleFixture(config="cfg")},
    )
    scenario_builder = ScenarioBuilder(
        builder, _custom_scenario_with_config(), fixture=fixture
    )
    with pytest.raises(FixtureFormatError):
        scenario_builder.get_agents()


def test_unknown_role_in_save_fixture_raises(tmp_path):
    builder = AgentGraphBuilder()
    with pytest.raises(FixtureFormatError):
        builder.save_fixture(
            "demo", "checklist_iteration", roles={"nope": "cfg"}, directory=tmp_path
        )


# -- load_saved on missing file -------------------------------------------
def test_load_saved_missing_file_raises(tmp_path):
    builder = AgentGraphBuilder()
    with pytest.raises(FixtureNotFoundError):
        builder.load_saved("nope", directory=tmp_path)


# -- eager validation / error types ---------------------------------------
def test_load_saved_unknown_scenario_raises(tmp_path):
    save_fixture(
        ScenarioFixture(identifier="demo", scenario="nope"), tmp_path / "demo.json"
    )
    with pytest.raises(ScenarioNotFoundError):
        AgentGraphBuilder().load_saved("demo", directory=tmp_path)


def test_load_saved_validates_roles_eagerly(tmp_path):
    save_fixture(
        ScenarioFixture(
            identifier="demo",
            scenario="checklist_iteration",
            roles={"nope": RoleFixture(config="cfg")},
        ),
        tmp_path / "demo.json",
    )
    with pytest.raises(FixtureFormatError):
        AgentGraphBuilder().load_saved("demo", directory=tmp_path)


# -- save path override ----------------------------------------------------
def test_save_fixture_path_overrides_directory(tmp_path):
    explicit = tmp_path / "explicit" / "demo.json"
    path = AgentGraphBuilder().save_fixture(
        "demo",
        "checklist_iteration",
        path=explicit,
        directory=tmp_path / "ignored",
    )
    assert path == explicit
    assert explicit.exists()


# -- loader routing --------------------------------------------------------
def test_get_agents_routes_config_through_builder_loader(monkeypatch):
    stub = StubLoader(
        {"scenario_cfg": ["pi", "scen"], "fixture_cfg": ["pi", "fixture"]}
    )
    builder = AgentGraphBuilder()
    calls: list[object] = []

    def fake_get_agent_loader(path=None):
        calls.append(path)
        return stub

    monkeypatch.setattr(builder, "get_agent_loader", fake_get_agent_loader)
    fixture = ScenarioFixture(
        identifier="x",
        scenario="custom",
        roles={"lead": RoleFixture(config="fixture_cfg")},
    )
    scenario_builder = ScenarioBuilder(
        builder, _custom_scenario_with_config(), fixture=fixture
    )
    by_role = {a.role: a for a in scenario_builder.get_agents()}
    # Fixture config wins for lead; helper falls back to the scenario config —
    # both resolved via the builder's loader.
    assert by_role["lead"].base_argv == ["pi", "fixture"]
    assert by_role["helper"].base_argv == ["pi", "scen"]
    assert calls
