"""Exception hierarchy for pi-agent-graph.

All public errors inherit from :class:`PiAgentGraphError` so callers can catch
the whole family with a single ``except``.
"""

from __future__ import annotations


class PiAgentGraphError(Exception):
    """Base class for every error raised by pi-agent-graph."""


class ConfigNotFoundError(PiAgentGraphError):
    """No pi-cli config file exists at the resolved path."""


class ConfigParseError(PiAgentGraphError):
    """The pi-cli config file is malformed or has an unexpected shape."""


class PiCliNotFoundError(PiAgentGraphError):
    """The ``pi-cli`` executable could not be found."""


class SavedConfigNotFoundError(PiAgentGraphError):
    """The requested saved agent name is not present in the pi-cli config."""


class ScenarioNotFoundError(PiAgentGraphError):
    """The requested scenario key is not registered."""


class ValidationError(PiAgentGraphError):
    """One or more preflight checks failed; nothing was launched."""


class LaunchError(PiAgentGraphError):
    """A launch backend could not start an agent."""
