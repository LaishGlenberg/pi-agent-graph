"""Ordering: responders boot first, then prompt-bearing initiators."""

from __future__ import annotations

from ..models import Agent


def order_agents(agents: list[Agent]) -> list[Agent]:
    """Return agents in launch order.

    Agents without a starting prompt (responders) come first; agents with a
    prompt (initiators) come last, each group preserving its input order. This
    ensures a prompt-bearing agent never races its peers at start-up.
    """
    responders = [agent for agent in agents if not agent.prompt]
    initiators = [agent for agent in agents if agent.prompt]
    return responders + initiators
