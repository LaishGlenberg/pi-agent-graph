"""Launch pipeline: validation, ordering, and backends."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ..models import Agent
from .bash import BashBackend
from .ordering import order_agents
from .print import PrintBackend
from .terminal import TerminalBackend
from .types import LAYOUTS, TMUX_LAYOUTS, LaunchOptions, LaunchResult, LayoutName
from .validation import BANNED_FLAGS, KNOWN_BACKENDS, validate


class Backend(Protocol):
    """Structural type shared by the launch backends."""

    def launch(
        self, agents: list[Agent], options: LaunchOptions, run_id: str
    ) -> LaunchResult: ...


BACKENDS: dict[str, type[Backend]] = {
    "print": PrintBackend,
    "bash": BashBackend,
    "terminal": TerminalBackend,
}


def new_run_id() -> str:
    """Generate a sortable, collision-resistant run id."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def launch(
    agents: list[Agent],
    *,
    backend: str | None = None,
    options: LaunchOptions | None = None,
) -> LaunchResult:
    """Validate *agents*, then launch them in order via the chosen backend.

    Raises :class:`~pi_agent_graph.errors.ValidationError` before launching
    anything if the roster is invalid.
    """
    agents = list(agents)
    options = options or LaunchOptions()
    resolved_backend = backend or options.backend
    validate(agents, resolved_backend, options)

    run_id = options.run_id or new_run_id()

    if options.session_dir:
        run_dir = Path(options.session_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        for agent in agents:
            if not agent.session_dir:
                agent.set_session_dir(str(run_dir))

    if options.cwd:
        for agent in agents:
            if not agent.cwd:
                agent.set_cwd(options.cwd)

    ordered = order_agents(agents)
    implementation = BACKENDS[resolved_backend]()
    return implementation.launch(ordered, options, run_id)


__all__ = [
    "BACKENDS",
    "BANNED_FLAGS",
    "KNOWN_BACKENDS",
    "LAYOUTS",
    "TMUX_LAYOUTS",
    "LaunchOptions",
    "LaunchResult",
    "LayoutName",
    "launch",
    "new_run_id",
    "order_agents",
    "validate",
]
