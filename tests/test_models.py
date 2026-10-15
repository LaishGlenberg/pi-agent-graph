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
    agent.set_command(["pi", "-ne", "--provider", "x", "--thinking", "off"])
    assert agent.base_argv == ["pi", "-ne", "--provider", "x", "--thinking", "off"]


def test_set_command_extracts_model():
    agent = Agent(role="worker")
    agent.set_command(["pi", "-ne", "--model", "opencode-go/mimo-v2.5:low"])
    assert agent.model == "opencode-go/mimo-v2.5:low"
    assert agent.model_explicit is False
    assert agent.base_argv == ["pi", "-ne"]


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


# -- model selection -------------------------------------------------------
def test_set_model_without_thinking():
    agent = Agent(role="r")
    agent.set_model("opencode-go/mimo-v2.5")
    assert agent.model == "opencode-go/mimo-v2.5"
    assert agent.model_explicit is True
    assert agent.build_argv()[-2:] == ["--model", "opencode-go/mimo-v2.5"]


def test_set_model_with_thinking_appends_suffix():
    agent = Agent(role="r")
    agent.set_model("opencode-go/mimo-v2.5", "low")
    assert agent.model == "opencode-go/mimo-v2.5:low"


def test_set_model_replaces_existing_thinking_suffix():
    agent = Agent(role="r")
    agent.set_model("m:high", "low")
    assert agent.model == "m:low"


def test_set_model_keeps_colon_model_without_known_suffix():
    agent = Agent(role="r")
    agent.set_model("provider/weird:name", "high")
    assert agent.model == "provider/weird:name:high"


def test_set_model_strips_bare_thinking_flag():
    agent = Agent(role="r", base_argv=["pi", "--thinking", "high"])
    agent.set_model("m", "low")
    assert agent.base_argv == ["pi"]
    assert agent.model == "m:low"
    assert "--thinking" not in agent.build_argv()


def test_set_model_overrides_config_model():
    agent = Agent(role="r")
    agent.set_command(["pi", "--model", "config"])
    agent.set_model("python", "high")
    argv = agent.build_argv()
    assert argv.count("--model") == 1
    assert argv[argv.index("--model") + 1] == "python:high"


def test_set_model_then_set_command_config_model_wins_but_is_not_explicit():
    agent = Agent(role="r")
    agent.set_model("python")
    agent.set_command(["pi", "--model", "config"])
    assert agent.model == "config"
    assert agent.model_explicit is False


def test_direct_model_constructor_is_explicit():
    assert Agent(role="r", model="m").model_explicit is True


def test_set_option_model_routes_to_field_and_marks_explicit():
    agent = Agent(role="r", base_argv=["pi"])
    agent.set_option("--model", "m")
    assert agent.model == "m"
    assert agent.model_explicit is True
    assert agent.base_argv == ["pi"]


def test_build_argv_model_order():
    agent = Agent(
        role="r",
        base_argv=["pi"],
        name="n",
        session_dir="/d",
        model="m",
        system_prompt="s",
        prompt="p",
    )
    assert agent.build_argv() == [
        "pi",
        "--name",
        "n",
        "--session-dir",
        "/d",
        "--model",
        "m",
        "--system-prompt",
        "s",
        "--",
        "p",
    ]


# -- set_option ------------------------------------------------------------
def test_set_option_replaces_existing_flag():
    agent = Agent(role="r", base_argv=["pi", "--provider", "old", "--thinking", "off"])
    agent.set_option("--provider", "new")
    assert agent.base_argv == ["pi", "--thinking", "off", "--provider", "new"]


def test_set_option_removes_equals_form():
    agent = Agent(role="r", base_argv=["pi", "--provider=old"])
    agent.set_option("--provider", "new")
    assert agent.base_argv == ["pi", "--provider", "new"]


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
        ("set_dir", "cwd", "/d"),
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
