"""Tests for scenario fixtures: model validation and JSON save/load."""

from __future__ import annotations

import json

import pytest

from pi_agent_graph.errors import FixtureFormatError, FixtureNotFoundError
from pi_agent_graph.fixtures import (
    RoleFixture,
    ScenarioFixture,
    fixture_path,
    load_fixture,
    save_fixture,
)


def _make_fixture() -> ScenarioFixture:
    return ScenarioFixture(
        identifier="demo",
        scenario="code",
        shared_goal="Ship the feature",
        shared_context="Use uv; keep it simple.",
        roles={
            "planner": RoleFixture(config="planner_example", prompt="Plan it."),
            "worker": RoleFixture(config="worker_example", name="w1"),
        },
    )


# -- ScenarioFixture validation --------------------------------------------
def test_identifier_must_be_non_empty():
    with pytest.raises(FixtureFormatError):
        ScenarioFixture(identifier="", scenario="code")


def test_identifier_whitespace_rejected():
    with pytest.raises(FixtureFormatError):
        ScenarioFixture(identifier="   ", scenario="code")


def test_scenario_must_be_non_empty():
    with pytest.raises(FixtureFormatError):
        ScenarioFixture(identifier="demo", scenario="")


# -- to_dict / from_dict round trip ----------------------------------------
def test_to_dict_from_dict_round_trip():
    fixture = _make_fixture()
    data = fixture.to_dict()
    restored = ScenarioFixture.from_dict(data)
    assert restored == fixture


def test_from_dict_missing_identifier():
    with pytest.raises(FixtureFormatError):
        ScenarioFixture.from_dict({"scenario": "code"})


def test_from_dict_missing_scenario():
    with pytest.raises(FixtureFormatError):
        ScenarioFixture.from_dict({"identifier": "demo"})


def test_from_dict_bad_roles_type():
    with pytest.raises(FixtureFormatError):
        ScenarioFixture.from_dict(
            {"identifier": "demo", "scenario": "code", "roles": ["not", "a", "map"]}
        )


def test_from_dict_defaults():
    restored = ScenarioFixture.from_dict({"identifier": "d", "scenario": "code"})
    assert restored.shared_goal == ""
    assert restored.shared_context == ""
    assert restored.roles == {}


# -- save / load -----------------------------------------------------------
def test_save_and_load_round_trip(tmp_path):
    fixture = _make_fixture()
    path = tmp_path / "demo.json"
    save_fixture(fixture, path)
    assert path.exists()
    assert load_fixture(path) == fixture


def test_save_creates_parent_dirs(tmp_path):
    fixture = _make_fixture()
    path = tmp_path / "nested" / "deep" / "demo.json"
    save_fixture(fixture, path)
    assert load_fixture(path) == fixture


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FixtureNotFoundError):
        load_fixture(tmp_path / "nope.json")


def test_load_bad_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(FixtureFormatError):
        load_fixture(path)


def test_load_missing_fields_raises(tmp_path):
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"identifier": "demo"}), encoding="utf-8")
    with pytest.raises(FixtureFormatError):
        load_fixture(path)


# -- fixture_path ----------------------------------------------------------
def test_fixture_path_default_directory():
    assert fixture_path("demo") == fixture_path("demo", "fixtures")


def test_fixture_path_custom_directory(tmp_path):
    assert fixture_path("demo", tmp_path) == tmp_path / "demo.json"
