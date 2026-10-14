"""The ``print`` backend: render commands without launching anything."""

from __future__ import annotations

from ..models import Agent
from ..quoting import join_posix
from .types import LaunchOptions, LaunchResult


class PrintBackend:
    name = "print"

    def launch(
        self, agents: list[Agent], options: LaunchOptions, run_id: str
    ) -> LaunchResult:
        commands: list[list[str]] = []
        for agent in agents:
            argv = agent.build_argv()
            commands.append(argv)
            print(join_posix(argv))
        return LaunchResult(
            run_id=run_id,
            backend=self.name,
            commands=commands,
            agents=list(agents),
            pids=[None] * len(agents),
        )
