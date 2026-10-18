"""Shared launch types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, get_args

from ..models import Agent

#: Named tmux window layouts accepted by ``select-layout``. These are valid
#: ``layout`` values too: they select a single terminal window of tmux panes
#: arranged that way.
TMUX_LAYOUTS: tuple[str, ...] = (
    "tiled",
    "even-horizontal",
    "even-vertical",
    "main-horizontal",
    "main-vertical",
)

LayoutName = Literal[
    "window",
    "tab",
    "split",
    "tiled",
    "even-horizontal",
    "even-vertical",
    "main-horizontal",
    "main-vertical",
]
"""How the ``terminal`` backend arranges a roster.

``window`` opens one OS window per agent (the default, cross-platform);
``tab`` gives each agent a tmux window inside one terminal; ``split`` (an
alias for ``tiled``) and any name in :data:`TMUX_LAYOUTS` tile the agents as
tmux panes in one terminal. Everything except ``window`` is Linux-only.
"""

#: Every valid ``layout`` value, derived from :data:`LayoutName`.
LAYOUTS: tuple[str, ...] = get_args(LayoutName)


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
    layout: LayoutName = "window"


@dataclass
class LaunchResult:
    """A record of what was launched, usable for reproduction."""

    run_id: str
    backend: str
    commands: list[list[str]]
    agents: list[Agent]
    pids: list[int | None] = field(default_factory=list)
    path: str | None = None
