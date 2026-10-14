"""pi-agent-graph: build and launch multi-agent pi workflows."""

from __future__ import annotations

from .builder import AgentGraphBuilder, ScenarioBuilder, render_system_prompt
from .cli import main
from .errors import (
    ConfigNotFoundError,
    ConfigParseError,
    FixtureError,
    FixtureFormatError,
    FixtureNotFoundError,
    LaunchError,
    PiAgentGraphError,
    PiCliNotFoundError,
    SavedConfigNotFoundError,
    ScenarioNotFoundError,
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
from .models import Agent, Role, Scenario
from .scenarios import SCENARIOS, get_scenario, scenario_names

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "AgentGraphBuilder",
    "ConfigLoader",
    "ConfigNotFoundError",
    "ConfigParseError",
    "FixtureError",
    "FixtureFormatError",
    "FixtureNotFoundError",
    "LaunchError",
    "LaunchOptions",
    "LaunchResult",
    "PiAgentGraphError",
    "PiCliNotFoundError",
    "Role",
    "RoleFixture",
    "SavedConfigNotFoundError",
    "Scenario",
    "ScenarioBuilder",
    "ScenarioFixture",
    "ScenarioNotFoundError",
    "SCENARIOS",
    "ValidationError",
    "__version__",
    "fixture_path",
    "get_scenario",
    "launch",
    "load_fixture",
    "main",
    "parse_dry_run",
    "render_system_prompt",
    "save_fixture",
    "scenario_names",
]
