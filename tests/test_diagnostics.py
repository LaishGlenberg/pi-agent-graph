"""Tests for the centralized diagnostics registry."""

from __future__ import annotations

from io import StringIO

import pytest

from pi_agent_graph import errors
from pi_agent_graph.diagnostics import (
    ERROR_CODES,
    RESET,
    YELLOW,
    Diagnostic,
    ErrorCode,
    WarningCode,
    collect_warnings,
    default_model_warning,
    emit_warnings,
    error_code,
)
from pi_agent_graph.models import Agent


# -- error codes -----------------------------------------------------------
def test_every_error_class_is_enumerated():
    # Every concrete error in the hierarchy has a code (the base and
    # intermediate classes map too, so coverage is simple).
    for name in (
        "ConfigNotFoundError",
        "ConfigParseError",
        "PiCliNotFoundError",
        "SavedConfigNotFoundError",
        "ScenarioNotFoundError",
        "ValidationError",
        "LaunchError",
        "FixtureError",
        "FixtureNotFoundError",
        "FixtureFormatError",
    ):
        assert getattr(errors, name) in ERROR_CODES


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (errors.ConfigNotFoundError("x"), ErrorCode.CONFIG_NOT_FOUND),
        (errors.ConfigParseError("x"), ErrorCode.CONFIG_PARSE),
        (errors.PiCliNotFoundError("x"), ErrorCode.PI_CLI_NOT_FOUND),
        (errors.SavedConfigNotFoundError("x"), ErrorCode.SAVED_CONFIG_NOT_FOUND),
        (errors.ScenarioNotFoundError("x"), ErrorCode.SCENARIO_NOT_FOUND),
        (errors.ValidationError("x"), ErrorCode.VALIDATION),
        (errors.LaunchError("x"), ErrorCode.LAUNCH),
        (errors.FixtureError("x"), ErrorCode.FIXTURE),
        (errors.FixtureNotFoundError("x"), ErrorCode.FIXTURE_NOT_FOUND),
        (errors.FixtureFormatError("x"), ErrorCode.FIXTURE_FORMAT),
        (errors.PiAgentGraphError("x"), ErrorCode.UNKNOWN),
    ],
)
def test_error_code_resolves_most_specific(error, code):
    assert error_code(error) is code


def test_error_code_unknown_non_library_error():
    assert error_code(ValueError("x")) is ErrorCode.UNKNOWN


# -- warnings --------------------------------------------------------------
def test_collect_warnings_flags_model_less_agents():
    agents = [Agent(role="planner"), Agent(role="worker", model="m")]
    warnings = collect_warnings(agents)
    assert len(warnings) == 1
    assert warnings[0].code is WarningCode.DEFAULT_MODEL
    assert warnings[0].agent == "planner"
    assert "default model" in warnings[0].message


def test_collect_warnings_uses_display_name():
    agent = Agent(role="worker", name="w1")
    assert default_model_warning(agent).agent == "w1"


def test_collect_warnings_empty_when_all_modeled():
    assert collect_warnings([Agent(role="a", model="m")]) == []


def test_diagnostic_format_includes_code():
    warning = Diagnostic(code=WarningCode.DEFAULT_MODEL, message="hi", agent="a")
    assert warning.format() == "[default_model] hi"


def test_emit_warnings_writes_yellow_to_stream():
    stream = StringIO()
    emit_warnings([default_model_warning(Agent(role="worker"))], stream=stream)
    text = stream.getvalue()
    assert text.startswith(f"{YELLOW}warning:")
    assert text.rstrip().endswith(RESET)
    assert "[default_model]" in text


def test_emit_warnings_can_disable_color():
    stream = StringIO()
    emit_warnings(
        [default_model_warning(Agent(role="worker"))], stream=stream, color=False
    )
    assert stream.getvalue().startswith("warning:")
    assert YELLOW not in stream.getvalue()
