"""Reserved command-line entry point.

The library is API-first; the ``pi-agent-graph`` console script is a placeholder
that only prints help in v1.
"""

from __future__ import annotations

from collections.abc import Sequence

HELP = """\
pi-agent-graph: build and launch multi-agent pi workflows.

This build exposes a Python API. A command-line interface is planned.

  from pi_agent_graph import AgentGraphBuilder

See README.md for a quickstart and SPEC.md for the design.
"""


def main(argv: Sequence[str] | None = None) -> int:
    print(HELP)
    return 0
