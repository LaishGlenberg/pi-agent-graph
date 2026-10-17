"""Manual Windows smoke test for the ``terminal`` backend.

This opens real terminal windows but never launches ``pi``: each agent runs a
harmless ``cmd /c echo`` with a fake system prompt. Run it by hand on Windows:

    uv run examples/smoke_terminal.py

You should get exactly **two** windows (one per agent), each printing one line
that contains both a newline and a semicolon. Before the fix, ``wt`` treated
the semicolons as command separators and opened several partial windows.
"""

import sys

from pi_agent_graph import Agent, AgentGraphBuilder

if not sys.platform.startswith("win"):
    raise SystemExit("examples/smoke_terminal.py is a Windows-only smoke test")

builder = AgentGraphBuilder()

agents = []
for name in ("smoke_a", "smoke_b"):
    agent = Agent(role=name)
    agent.set_command(["cmd", "/c", "echo"])
    agent.set_system_prompt(f"line one\nline two; {name} stays in one window")
    agents.append(agent)

builder.start(agents)
