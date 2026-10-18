"""Tests for the built-in scenario registry."""

from __future__ import annotations

import pytest

from pi_agent_graph.errors import ScenarioNotFoundError
from pi_agent_graph.scenarios import SCENARIOS, get_scenario, scenario_names


def test_known_scenarios():
    assert set(scenario_names()) == {
        "checklist_iteration",
        "subagent_scouting",
        "scout_worker_planner",
        "testing",
    }


def test_scenario_keys_match_registry():
    for key, scenario in SCENARIOS.items():
        assert scenario.key == key


def test_all_scenarios_have_descriptions_and_roles():
    for scenario in SCENARIOS.values():
        assert scenario.description
        assert scenario.roles
        for name, role in scenario.roles.items():
            assert role.name == name
            assert role.description


def test_checklist_iteration_role_order():
    assert get_scenario("checklist_iteration").agent_names() == ["planner", "worker"]


def test_subagent_scouting_role_order():
    assert get_scenario("subagent_scouting").agent_names() == ["worker", "scout"]


def test_scout_worker_planner_role_order():
    assert get_scenario("scout_worker_planner").agent_names() == [
        "planner",
        "worker",
        "scout",
    ]


def test_unknown_scenario_raises():
    with pytest.raises(ScenarioNotFoundError) as exc:
        get_scenario("nope")
    assert "unknown scenario" in str(exc.value)
