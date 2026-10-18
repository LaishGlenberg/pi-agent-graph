"""Shared launch types."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Agent

#: Same-window layouts for the ``terminal`` backend. ``window`` opens one OS
#: window per agent (the default); ``tab`` and ``split`` multiplex every agent
#: into a single window via tmux. Only supported on Linux.
LAYOUTS: tuple[str, ...] = ("window", "tab", "split")


@dataclass
class LaunchOptions:
    """Options controlling how a roster is launched."""

    backend: str = "terminal"
    stagger: float = 1.5
    session_dir: str | None = None
    run_id: str | None = None
    cwd: str | None = None
    bash_path: str | None = None
    platform: str | None = None
    layout: str = "window"


@dataclass
class LaunchResult:
    """A record of what was launched, usable for reproduction."""

    run_id: str
    backend: str
    commands: list[list[str]]
    agents: list[Agent]
    pids: list[int | None] = field(default_factory=list)
    path: str | None = None
