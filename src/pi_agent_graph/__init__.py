"""pi-agent-graph: build and launch multi-agent pi workflows."""

from __future__ import annotations

from .builder import AgentGraphBuilder, ScenarioBuilder, render_system_prompt
from .cli import main
from .errors import (
    ConfigNotFoundError,
    ConfigParseError,
    LaunchError,
    PiAgentGraphError,
    PiCliNotFoundError,
    SavedConfigNotFoundError,
    ScenarioNotFoundError,
    ValidationError,
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
    "LaunchError",
    "LaunchOptions",
    "LaunchResult",
    "PiAgentGraphError",
    "PiCliNotFoundError",
    "Role",
    "SavedConfigNotFoundError",
    "Scenario",
    "ScenarioBuilder",
    "ScenarioNotFoundError",
    "SCENARIOS",
    "ValidationError",
    "__version__",
    "get_scenario",
    "launch",
    "main",
    "parse_dry_run",
    "render_system_prompt",
    "scenario_names",
]
