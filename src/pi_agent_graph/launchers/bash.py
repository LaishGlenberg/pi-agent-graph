"""The ``bash`` backend: write a reproducible launch script."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Callable

from ..models import Agent
from .script import render_launch_script
from .types import LaunchOptions, LaunchResult

Which = Callable[[str], str | None]

# Backwards-compatible alias: the renderer used to live in this module.
render_bash_script = render_launch_script


class BashBackend:
    name = "bash"

    def __init__(self, which: Which | None = None) -> None:
        self._which = which or shutil.which

    def launch(
        self, agents: list[Agent], options: LaunchOptions, run_id: str
    ) -> LaunchResult:
        assert options.bash_path is not None  # guaranteed by validation
        path = Path(options.bash_path)
        platform = options.platform or sys.platform
        script = render_launch_script(
            agents,
            run_id=run_id,
            platform=platform,
            cwd=options.cwd,
            which=self._which,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="" keeps the script's exact line endings: no CRLF mangling of
        # a .sh shebang, and no \r\r\n in a .cmd on Windows.
        path.write_text(script, encoding="utf-8", newline="")
        commands = [agent.build_argv() for agent in agents]
        return LaunchResult(
            run_id=run_id,
            backend=self.name,
            commands=commands,
            agents=list(agents),
            pids=[None] * len(agents),
            path=str(path),
        )
