"""Central, enumerable diagnostics: warning codes and error codes.

Every user-facing warning has a stable :class:`WarningCode`, and every error
class in :mod:`pi_agent_graph.errors` maps to a stable :class:`ErrorCode`
through :data:`ERROR_CODES`. Callers can branch on a code instead of matching
message text, and new diagnostics have one obvious home.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TextIO

from . import errors
from .models import Agent

#: ANSI color applied to warnings (pi's warnings are yellow).
YELLOW = "\033[33m"
RESET = "\033[0m"


class ErrorCode(StrEnum):
    """Stable identifiers for the exception hierarchy."""

    CONFIG_NOT_FOUND = "config_not_found"
    CONFIG_PARSE = "config_parse"
    PI_CLI_NOT_FOUND = "pi_cli_not_found"
    SAVED_CONFIG_NOT_FOUND = "saved_config_not_found"
    SCENARIO_NOT_FOUND = "scenario_not_found"
    VALIDATION = "validation"
    LAUNCH = "launch"
    FIXTURE = "fixture"
    FIXTURE_NOT_FOUND = "fixture_not_found"
    FIXTURE_FORMAT = "fixture_format"
    UNKNOWN = "unknown"


#: Enumerates every error class. Walked most-specific-first by
#: :func:`error_code`, so subclasses resolve to their own code.
ERROR_CODES: dict[type[errors.PiAgentGraphError], ErrorCode] = {
    errors.ConfigNotFoundError: ErrorCode.CONFIG_NOT_FOUND,
    errors.ConfigParseError: ErrorCode.CONFIG_PARSE,
    errors.PiCliNotFoundError: ErrorCode.PI_CLI_NOT_FOUND,
    errors.SavedConfigNotFoundError: ErrorCode.SAVED_CONFIG_NOT_FOUND,
    errors.ScenarioNotFoundError: ErrorCode.SCENARIO_NOT_FOUND,
    errors.ValidationError: ErrorCode.VALIDATION,
    errors.LaunchError: ErrorCode.LAUNCH,
    errors.FixtureNotFoundError: ErrorCode.FIXTURE_NOT_FOUND,
    errors.FixtureFormatError: ErrorCode.FIXTURE_FORMAT,
    errors.FixtureError: ErrorCode.FIXTURE,
    errors.PiAgentGraphError: ErrorCode.UNKNOWN,
}


class WarningCode(StrEnum):
    """Stable identifiers for non-fatal diagnostics."""

    DEFAULT_MODEL = "default_model"


@dataclass(frozen=True)
class Diagnostic:
    """A warning surfaced to the user, addressable by :attr:`code`."""

    code: WarningCode
    message: str
    agent: str | None = None

    def format(self) -> str:
        return f"[{self.code.value}] {self.message}"


def error_code(error: BaseException) -> ErrorCode:
    """Return the most specific :class:`ErrorCode` for *error*."""
    for cls in type(error).__mro__:
        code = ERROR_CODES.get(cls)
        if code is not None:
            return code
    return ErrorCode.UNKNOWN


def default_model_warning(agent: Agent) -> Diagnostic:
    """Build the warning for an agent that will fall back to pi's default."""
    label = agent.name or agent.role
    return Diagnostic(
        code=WarningCode.DEFAULT_MODEL,
        agent=label,
        message=(
            f"agent {label!r} has no model configured; pi will use its default model"
        ),
    )


def collect_warnings(agents: Sequence[Agent]) -> list[Diagnostic]:
    """Return every warning for *agents* (currently: default-model fallback)."""
    return [default_model_warning(agent) for agent in agents if not agent.model]


def emit_warnings(
    warnings: Sequence[Diagnostic],
    *,
    stream: TextIO | None = None,
    color: bool = True,
) -> None:
    """Write *warnings* to *stream* (stderr by default), in yellow."""
    target = stream if stream is not None else sys.stderr
    for warning in warnings:
        text = f"warning: {warning.format()}"
        if color:
            text = f"{YELLOW}{text}{RESET}"
        print(text, file=target)
