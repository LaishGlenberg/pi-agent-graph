"""Tests for the Agent / Role / Scenario data model."""

from __future__ import annotations

import pytest

from pi_agent_graph.models import Agent, Role, Scenario


# -- name defaults ---------------------------------------------------------
def test_default_name_is_role():
    assert Agent(role="worker").name == "worker"


def test_explicit_name_is_kept():
    assert Agent(role="worker", name="w1").name == "w1"


# -- set_command extracts managed flags ------------------------------------
def test_set_command_extracts_managed_flags():
    agent = Agent(role="worker")
    agent.set_command(
        [
            "pi",
            "-ne",
            "--name",
            "w2",
            "--system-prompt",
            "hi there",
            "--session-dir",
            "/tmp/s",
        ]
    )
    assert agent.name == "w2"
    assert agent.system_prompt == "hi there"
    assert agent.session_dir == "/tmp/s"
    assert agent.base_argv == ["pi", "-ne"]


def test_set_command_equals_form():
    agent = Agent(role="worker")
    agent.set_command(["pi", "--name=w3", "--system-prompt=x=y", "--session-dir=/d"])
    assert agent.name == "w3"
    assert agent.system_prompt == "x=y"
    assert agent.session_dir == "/d"
    assert agent.base_argv == ["pi"]


def test_set_command_last_managed_flag_wins():
    agent = Agent(role="worker")
    agent.set_command(["pi", "--name", "a", "--name", "b"])
    assert agent.name == "b"
    assert agent.base_argv == ["pi"]


def test_set_command_trailing_flag_without_value_is_dropped():
    agent = Agent(role="worker")
    agent.set_command(["pi", "--name"])
    assert agent.name == "worker"  # default preserved
    assert agent.base_argv == ["pi"]


def test_set_command_keeps_unmanaged_flags_in_order():
    agent = Agent(role="worker")
    agent.set_command(["pi", "-ne", "--model", "x", "--thinking", "off"])
    assert agent.base_argv == ["pi", "-ne", "--model", "x", "--thinking", "off"]


# -- system prompt replaces, never appends ---------------------------------
def test_set_system_prompt_replaces_not_appends():
    agent = Agent(role="worker")
    agent.set_command(["pi", "--system-prompt", "old"])
    agent.set_system_prompt("new")
    argv = agent.build_argv()
    assert argv.count("--system-prompt") == 1
    assert argv[argv.index("--system-prompt") + 1] == "new"


def test_build_argv_strips_managed_flags_from_base_argv():
    agent = Agent(
        role="worker",
        base_argv=["pi", "--system-prompt", "loose"],
        system_prompt="field",
    )
    assert agent.build_argv() == [
        "pi",
        "--name",
        "worker",
        "--system-prompt",
        "field",
    ]


# -- build_argv is pure and deterministic ----------------------------------
def test_build_argv_is_pure():
    agent = Agent(role="worker", base_argv=["pi"], system_prompt="s", prompt="p")
    first = agent.build_argv()
    second = agent.build_argv()
    assert first == second
    assert agent.base_argv == ["pi"]


def test_build_argv_full_order():
    agent = Agent(
        role="r",
        base_argv=["pi", "-ne"],
        name="n",
        session_dir="/d",
        system_prompt="s",
        prompt="p",
    )
    assert agent.build_argv() == [
        "pi",
        "-ne",
        "--name",
        "n",
        "--session-dir",
        "/d",
        "--system-prompt",
        "s",
        "--",
        "p",
    ]


def test_build_argv_prompt_is_prefixed_with_double_dash():
    agent = Agent(role="r", base_argv=["pi"], prompt="-danger")
    assert agent.build_argv()[-2:] == ["--", "-danger"]


def test_build_argv_omits_empty_prompt():
    agent = Agent(role="r", base_argv=["pi"], prompt="")
    assert agent.build_argv() == ["pi", "--name", "r"]


def test_build_argv_omits_empty_system_prompt():
    agent = Agent(role="r", base_argv=["pi"], system_prompt="")
    assert agent.build_argv() == ["pi", "--name", "r"]


# -- set_option ------------------------------------------------------------
def test_set_option_replaces_existing_flag():
    agent = Agent(role="r", base_argv=["pi", "--model", "old", "--thinking", "off"])
    agent.set_option("--model", "new")
    assert agent.base_argv == ["pi", "--thinking", "off", "--model", "new"]


def test_set_option_removes_equals_form():
    agent = Agent(role="r", base_argv=["pi", "--model=old"])
    agent.set_option("--model", "new")
    assert agent.base_argv == ["pi", "--model", "new"]


def test_set_option_managed_flag_routes_to_field():
    agent = Agent(role="r", base_argv=["pi"])
    agent.set_option("--system-prompt", "sp")
    assert agent.system_prompt == "sp"
    assert agent.base_argv == ["pi"]


# -- setters ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("method", "attr", "value"),
    [
        ("set_name", "name", "x"),
        ("set_session_dir", "session_dir", "/s"),
        ("set_system_prompt", "system_prompt", "sp"),
        ("set_prompt", "prompt", "p"),
        ("set_cwd", "cwd", "/c"),
    ],
)
def test_setters(method, attr, value):
    agent = Agent(role="r")
    getattr(agent, method)(value)
    assert getattr(agent, attr) == value


# -- Role / Scenario -------------------------------------------------------
def test_scenario_helpers():
    role = Role(name="worker", description="d", config="w1")
    scenario = Scenario(key="k", description="desc", roles={"worker": role})
    assert scenario.agent_names() == ["worker"]
    assert scenario.get("worker") is role
