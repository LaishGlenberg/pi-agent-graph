"""Reusable in-memory fakes for integration-style tests.

They stand in for the two process boundaries in the library:

* :class:`FakePiCli` replaces the ``pi-cli --dry-run`` subprocess that
  :class:`~pi_agent_graph.loader.ConfigLoader` shells out to. Name resolution,
  quoting, and error handling still run for real; only the subprocess is fake.
* :class:`FakeLauncher` replaces a launch backend, recording the argv each
  agent *would* run instead of opening a terminal.

Used together they exercise the full config -> agents -> launch pipeline
without spawning a process.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pi_agent_graph.launchers import BACKENDS
from pi_agent_graph.launchers.types import LaunchOptions, LaunchResult
from pi_agent_graph.loader import ConfigLoader
from pi_agent_graph.models import Agent


class FakePiCli:
    """An in-memory ``pi-cli`` install.

    Seed it with saved agent commands (a command string or an argv sequence).
    :meth:`loader` returns a real :class:`ConfigLoader` wired to :meth:`runner`,
    so resolution behaves exactly as in production.
    """

    def __init__(self, agents: Mapping[str, str | Sequence[str]] | None = None) -> None:
        self.agents: dict[str, str] = {}
        for name, command in (agents or {}).items():
            self.agents[name] = (
                command if isinstance(command, str) else shlex.join(list(command))
            )
        #: Every ``(argv, env)`` the loader asked for, for assertions.
        self.requests: list[tuple[list[str], dict[str, str]]] = []

    def runner(
        self, argv: Sequence[str], env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        self.requests.append((list(argv), dict(env)))
        name = argv[-1]
        if name not in self.agents:
            return subprocess.CompletedProcess(argv, 1, "", f"unknown agent {name!r}")
        return subprocess.CompletedProcess(argv, 0, self.agents[name], "")

    def write_config(self, path: str | Path) -> Path:
        """Write a pi-cli config containing the seeded agents and return its path."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"agents": self.agents}), encoding="utf-8")
        return target

    def loader(self, config_path: str | Path) -> ConfigLoader:
        """A real ``ConfigLoader`` bound to this fake's runner."""
        return ConfigLoader(config_path, runner=self.runner)

    def install(self, monkeypatch) -> None:
        """Make ``ConfigLoader`` resolve this fake as the ``pi-cli`` binary."""
        import pi_agent_graph.loader as loader_mod

        monkeypatch.setattr(loader_mod.shutil, "which", lambda name: "/fake/pi-cli")


@dataclass
class LaunchRecord:
    """A single captured launch."""

    run_id: str
    agents: list[Agent]
    options: LaunchOptions
    commands: list[list[str]]


class FakeLauncher:
    """Records what a launch backend would run; starts nothing."""

    def __init__(self) -> None:
        self.records: list[LaunchRecord] = []

    def backend(self) -> type:
        records = self.records

        class _RecordingBackend:
            name = "print"

            def launch(
                self, agents: list[Agent], options: LaunchOptions, run_id: str
            ) -> LaunchResult:
                ordered = list(agents)
                commands = [agent.build_argv() for agent in ordered]
                records.append(
                    LaunchRecord(
                        run_id=run_id,
                        agents=ordered,
                        options=options,
                        commands=commands,
                    )
                )
                return LaunchResult(
                    run_id=run_id,
                    backend="print",
                    commands=commands,
                    agents=ordered,
                    pids=[None] * len(ordered),
                )

        return _RecordingBackend

    def install(self, monkeypatch) -> None:
        """Replace the ``print`` backend so ``start(..., backend="print")`` records."""
        monkeypatch.setitem(BACKENDS, "print", self.backend())

    @property
    def last(self) -> LaunchRecord:
        return self.records[-1]

    def commands(self) -> list[list[str]]:
        return self.last.commands
