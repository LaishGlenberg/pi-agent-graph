"""Tests for the Agent / Role / Scenario data model."""

from __future__ import annotations

from pathlib import Path

import pytest

from pi_agent_graph.errors import UnknownToolError
from pi_agent_graph.models import Agent, Role, Scenario
from pi_agent_graph.resources import BUILTIN_TOOLS


# -- name defaults ---------------------------------------------------------
def test_default_name_is_role():
    assert Agent(role="worker").name == "worker"


def test_explicit_name_is_kept():
    assert Agent(role="worker", name="w1").name == "w1"


def test_get_name_and_str_return_name():
    assert Agent(role="planner").get_name() == "planner"
    assert str(Agent(role="worker", name="w1")) == "w1"
    assert str(Agent(role="planner")) == "planner"


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


# -- readable commands -----------------------------------------------------
def test_display_command_shortens_and_merges_resources():
    agent = Agent(
        role="worker",
        base_argv=["pi", "-ne"],
        extensions=[
            "/home/lg/extensions/pi-parse-commands",
            "/home/lg/.pi/agent/npm/node_modules/@juicesharp/rpiv-todo",
        ],
        skills=["/home/lg/.pi/agent/npm/node_modules/pi-intercom/skills/pi-intercom"],
    )
    assert agent.display_command() == (
        "pi -s pi-intercom -e pi-parse-commands,rpiv-todo --name worker"
    )


def test_display_command_keeps_no_extensions_when_none_set():
    agent = Agent(role="worker", base_argv=["pi", "-ne"])
    assert agent.display_command() == "pi -ne --name worker"


def test_display_command_inverts_exclude_tools_to_builtin_allowlist():
    agent = Agent(
        role="worker",
        base_argv=["pi", "--exclude-tools", "read,powershell,edit,write,find"],
    )
    out = agent.display_command()
    assert "-bt bash,grep,ls" in out
    assert "--exclude-tools" not in out


def test_display_command_uses_python_builtin_tools_in_order():
    agent = Agent(role="r")
    agent.set_tools("grep", "ls", "bash")
    assert agent.display_command() == "pi -bt grep,ls,bash --name r"


def test_display_command_keeps_exclude_tools_with_unknown_names():
    agent = Agent(role="r", base_argv=["pi", "--exclude-tools", "read,ext_tool"])
    out = agent.display_command()
    assert "--exclude-tools read,ext_tool" in out
    assert "-bt" not in out


def test_display_command_keeps_no_context_and_no_builtin_flags():
    agent = Agent(role="r", base_argv=["pi", "-nc", "-nbt"])
    assert agent.display_command() == "pi -nc -nbt --name r"


def test_display_command_quotes_tokens_with_spaces():
    agent = Agent(role="worker", prompt="do the thing")
    assert agent.display_command() == 'pi --name worker -- "do the thing"'


def test_display_command_keeps_prompt_apostrophes_readable():
    agent = Agent(role="worker", prompt="when you're ready, tell the worker")
    assert agent.display_command() == (
        'pi --name worker -- "when you\'re ready, tell the worker"'
    )


def test_display_command_escapes_prompt_newlines():
    agent = Agent(role="worker", prompt="line one\nline two")
    assert agent.display_command() == 'pi --name worker -- "line one\\nline two"'


def test_display_command_shows_short_system_prompt_in_full():
    agent = Agent(role="worker", system_prompt="short prompt")
    assert agent.display_command().endswith('--system-prompt "short prompt"')


def test_display_command_previews_only_the_system_prompt_tail():
    tail = "b" * 30
    agent = Agent(role="worker", system_prompt="a" * 10 + tail)
    out = agent.display_command()
    assert out.endswith(f'--system-prompt "...{tail}"')
    assert "a" * 10 not in out


def test_display_command_escapes_system_prompt_newlines():
    agent = Agent(role="worker", system_prompt="line one\nline two")
    out = agent.display_command()
    assert r"line one\nline two" in out
    assert "\n" not in out


def test_display_command_defaults_to_pi():
    assert Agent(role="worker").display_command() == "pi --name worker"


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


# -- resources -------------------------------------------------------------
def make_agent_dir(tmp_path: Path, *names: str) -> Path:
    agent_dir = tmp_path / "agent"
    for name in names:
        extension = agent_dir / "extensions" / name
        extension.mkdir(parents=True)
        (extension / "index.ts").write_text("", encoding="utf-8")
    return agent_dir


def make_skill(agent_dir: Path, name: str) -> Path:
    skill = agent_dir / "skills" / f"{name}.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text("", encoding="utf-8")
    return skill


def test_default_command_is_pi(monkeypatch):
    monkeypatch.delenv("PI_BIN", raising=False)
    assert Agent(role="worker").build_argv() == ["pi", "--name", "worker"]


def test_pi_bin_is_the_default_command(monkeypatch):
    monkeypatch.setenv("PI_BIN", "/opt/pi")
    assert Agent(role="worker").build_argv()[0] == "/opt/pi"


def test_set_extensions_resolves_and_adds_no_extensions(tmp_path):
    agent_dir = make_agent_dir(tmp_path, "pi-intercom")
    agent = Agent(role="r")
    agent.set_extensions("pi-intercom", agent_dir=agent_dir)

    argv = agent.build_argv()
    resolved = str((agent_dir / "extensions" / "pi-intercom").resolve())
    assert agent.extensions == [resolved]
    assert argv[:4] == ["pi", "-ne", "--extension", resolved]


def test_set_extensions_accepts_comma_separated_values(tmp_path):
    agent_dir = make_agent_dir(tmp_path, "one", "two")
    agent = Agent(role="r")
    agent.set_extensions("one, two", agent_dir=agent_dir)

    assert len(agent.extensions or []) == 2
    assert agent.build_argv().count("--extension") == 2


def test_set_extensions_replaces_config_extensions_only(tmp_path):
    agent_dir = make_agent_dir(tmp_path, "new")
    agent = Agent(role="r")
    agent.set_command(
        [
            "pi",
            "-ne",
            "--extension",
            "/old/extension",
            "-ns",
            "--skill",
            "/old/skill.md",
        ]
    )
    agent.set_extensions("new", agent_dir=agent_dir)

    argv = agent.build_argv()
    assert "/old/extension" not in argv
    assert "--extension" in argv
    assert argv.count("--extension") == 1
    assert argv.count("-ne") == 1
    # The untouched skill family still comes from the saved command.
    assert argv.count("--skill") == 1
    assert "/old/skill.md" in argv


def test_set_skills_resolves_and_adds_no_skills(tmp_path):
    agent_dir = make_agent_dir(tmp_path)
    skill = make_skill(agent_dir, "playwright-cli")
    agent = Agent(role="r")
    agent.set_skills("playwright-cli", agent_dir=agent_dir)

    argv = agent.build_argv()
    assert agent.skills == [str(skill.resolve())]
    assert argv[:4] == ["pi", "-ns", "--skill", str(skill.resolve())]


def test_set_tools_emits_exclude_tools():
    agent = Agent(role="r")
    agent.set_tools("read", "bash")

    argv = agent.build_argv()
    assert agent.builtin_tools == ["read", "bash"]
    assert argv[1] == "--exclude-tools"
    excluded = argv[2].split(",")
    assert set(excluded) == set(BUILTIN_TOOLS) - {"read", "bash"}


def test_set_tools_replaces_config_exclude_tools():
    agent = Agent(role="r")
    agent.set_command(["pi", "--exclude-tools", "read,bash"])
    agent.set_tools("read")

    argv = agent.build_argv()
    assert argv.count("--exclude-tools") == 1
    assert "bash" in argv[argv.index("--exclude-tools") + 1]


def test_set_tools_rejects_unknown_tool():
    with pytest.raises(UnknownToolError):
        Agent(role="r").set_tools("read", "nope")


def test_set_exclude_tools_emits_exclude_tools():
    agent = Agent(role="r")
    agent.set_exclude_tools("bash")

    assert agent.exclude_tools == ["bash"]
    assert agent.build_argv()[1:3] == ["--exclude-tools", "bash"]


def test_set_exclude_tools_accepts_extension_names():
    agent = Agent(role="r")
    agent.set_exclude_tools("intercom, bash", "intercom")

    assert agent.build_argv()[1:3] == ["--exclude-tools", "intercom,bash"]


def test_set_exclude_tools_merges_with_builtin_keep_list():
    agent = Agent(role="r")
    agent.set_tools("read")
    agent.set_exclude_tools("intercom")

    argv = agent.build_argv()
    assert argv.count("--exclude-tools") == 1
    excluded = argv[argv.index("--exclude-tools") + 1].split(",")
    assert "intercom" in excluded
    assert set(excluded) >= set(BUILTIN_TOOLS) - {"read"}


def test_set_exclude_tools_with_use_tools_false_keeps_both():
    agent = Agent(role="r")
    agent.use_tools.set(False)
    agent.set_exclude_tools("bash")

    argv = agent.build_argv()
    assert "-nbt" in argv
    assert argv[argv.index("--exclude-tools") + 1] == "bash"


def test_set_exclude_tools_replaces_config_exclude_tools():
    agent = Agent(role="r")
    agent.set_command(["pi", "--exclude-tools", "read,bash"])
    agent.set_exclude_tools("intercom")

    argv = agent.build_argv()
    assert argv.count("--exclude-tools") == 1
    assert argv[argv.index("--exclude-tools") + 1] == "intercom"


def test_set_exclude_tools_empty_clears():
    agent = Agent(role="r")
    agent.set_exclude_tools("bash")
    agent.set_exclude_tools()

    assert agent.exclude_tools == []
    assert "--exclude-tools" not in agent.build_argv()


def test_display_command_keeps_explicit_exclude_with_keep_list():
    agent = Agent(role="r")
    agent.set_tools("read")
    agent.set_exclude_tools("intercom")

    out = agent.display_command()
    assert "--exclude-tools" in out
    assert "intercom" in out


def test_empty_extension_string_disables_extensions():
    agent = Agent(role="r")
    agent.set_extensions("")

    assert agent.use_extensions.get() is False
    assert "-ne" in agent.build_argv()
    assert "--extension" not in agent.build_argv()


def test_empty_skill_string_disables_skills():
    agent = Agent(role="r")
    agent.set_skills("")

    assert agent.use_skills.get() is False
    argv = agent.build_argv()
    assert "-ns" in argv
    assert "--skill" not in argv


def test_empty_tool_string_disables_builtin_tools():
    agent = Agent(role="r")
    agent.set_tools("")

    assert agent.use_tools.get() is False
    assert "-nbt" in agent.build_argv()


def test_use_extensions_false_overrides_config():
    agent = Agent(role="r")
    agent.set_command(["pi", "-ne", "--extension", "/old"])
    agent.use_extensions.set(False)

    assert agent.build_argv() == ["pi", "-ne", "--name", "r"]


def test_use_extensions_true_strips_config_disable_flag():
    agent = Agent(role="r")
    agent.set_command(["pi", "-ne", "--extension", "/old"])
    agent.use_extensions.set(True)

    argv = agent.build_argv()
    assert "-ne" not in argv
    assert "--extension" not in argv


def test_use_skills_false_overrides_config():
    agent = Agent(role="r")
    agent.set_command(["pi", "-ns", "--skill", "/old.md"])
    agent.use_skills.set(False)

    argv = agent.build_argv()
    assert argv.count("-ns") == 1
    assert "--skill" not in argv


def test_use_tools_false_overrides_config():
    agent = Agent(role="r")
    agent.set_command(["pi", "--exclude-tools", "read"])
    agent.use_tools.set(False)

    argv = agent.build_argv()
    assert "-nbt" in argv
    assert "--exclude-tools" not in argv


def test_use_context_false_adds_no_context_files():
    agent = Agent(role="r")
    agent.use_context.set(False)

    assert "-nc" in agent.build_argv()


def test_use_context_true_strips_config_flag():
    agent = Agent(role="r")
    agent.set_command(["pi", "-nc"])
    agent.use_context.set(True)

    assert "-nc" not in agent.build_argv()


def test_switch_get_and_explicit():
    switch = Agent(role="r").use_context
    assert switch.get() is True
    assert switch.explicit is False

    switch.set(False)
    assert switch.get() is False
    assert switch.explicit is True
    assert bool(switch) is False


def test_resource_composition_is_pure(tmp_path):
    agent_dir = make_agent_dir(tmp_path, "ext")
    agent = Agent(role="r")
    agent.set_command(["pi", "-ne", "--extension", "/old"])
    agent.set_extensions("ext", agent_dir=agent_dir)

    before = list(agent.base_argv)
    first = agent.build_argv()
    second = agent.build_argv()

    assert first == second
    assert agent.base_argv == before
    assert "/old" not in first
