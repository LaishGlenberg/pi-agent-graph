"""pi-agent-graph: build and launch multi-agent pi workflows."""

from __future__ import annotations

from .builder import AgentGraphBuilder, ScenarioBuilder, render_system_prompt
from .cli import main
from .diagnostics import (
    ERROR_CODES,
    Diagnostic,
    ErrorCode,
    WarningCode,
    collect_warnings,
    emit_warnings,
    error_code,
)
from .errors import (
    AmbiguousResourceError,
    ConfigNotFoundError,
    ConfigParseError,
    FixtureError,
    FixtureFormatError,
    FixtureNotFoundError,
    LaunchError,
    PiAgentGraphError,
    PiCliNotFoundError,
    ResourceError,
    ResourceNotFoundError,
    SavedConfigNotFoundError,
    ScenarioNotFoundError,
    UnknownToolError,
    ValidationError,
)
from .fixtures import (
    RoleFixture,
    ScenarioFixture,
    fixture_path,
    load_fixture,
    save_fixture,
)
from .launchers import LaunchOptions, LaunchResult, launch
from .loader import ConfigLoader, parse_dry_run
from .models import Agent, Role, Scenario, Switch
from .resources import (
    BUILTIN_TOOLS,
    builtin_tool_flags,
    default_agent_dir,
    excluded_builtin_tools,
    resolve_builtin_tools,
    resolve_extension,
    resolve_extensions,
    resolve_skill,
    resolve_skills,
)
from .scenarios import SCENARIOS, get_scenario, scenario_names

__version__ = "0.1.0"

__all__ = [
    "BUILTIN_TOOLS",
    "ERROR_CODES",
    "SCENARIOS",
    "Agent",
    "AgentGraphBuilder",
    "AmbiguousResourceError",
    "ConfigLoader",
    "ConfigNotFoundError",
    "ConfigParseError",
    "Diagnostic",
    "ErrorCode",
    "FixtureError",
    "FixtureFormatError",
    "FixtureNotFoundError",
    "LaunchError",
    "LaunchOptions",
    "LaunchResult",
    "PiAgentGraphError",
    "PiCliNotFoundError",
    "ResourceError",
    "ResourceNotFoundError",
    "Role",
    "RoleFixture",
    "SavedConfigNotFoundError",
    "Scenario",
    "ScenarioBuilder",
    "ScenarioFixture",
    "ScenarioNotFoundError",
    "Switch",
    "UnknownToolError",
    "ValidationError",
    "WarningCode",
    "__version__",
    "builtin_tool_flags",
    "collect_warnings",
    "default_agent_dir",
    "emit_warnings",
    "error_code",
    "excluded_builtin_tools",
    "fixture_path",
    "get_scenario",
    "launch",
    "load_fixture",
    "main",
    "parse_dry_run",
    "render_system_prompt",
    "resolve_builtin_tools",
    "resolve_extension",
    "resolve_extensions",
    "resolve_skill",
    "resolve_skills",
    "save_fixture",
    "scenario_names",
]
