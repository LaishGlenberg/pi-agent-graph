"""The ``print`` backend: show the launch script without launching anything.

Used by :meth:`AgentGraphBuilder.start_dry`. It renders the same script the
``bash`` backend writes, so the dry run is an exact preview.
"""

from __future__ import annotations

import sys

from ..models import Agent
from .script import render_launch_script
from .types import LaunchOptions, LaunchResult


class PrintBackend:
    name = "print"

    def launch(
        self, agents: list[Agent], options: LaunchOptions, run_id: str
    ) -> LaunchResult:
        platform = options.platform or sys.platform
        script = render_launch_script(
            agents, run_id=run_id, platform=platform, cwd=options.cwd
        )
        print(script, end="")
        commands = [agent.build_argv() for agent in agents]
        return LaunchResult(
            run_id=run_id,
            backend=self.name,
            commands=commands,
            agents=list(agents),
            pids=[None] * len(agents),
        )
