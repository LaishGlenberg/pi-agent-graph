"""Resolve saved ``pi-cli`` agent configs into ``pi`` argv lists.

Rather than reimplement ``pi-cli``'s extension/skill name resolution, this
module shells out to ``pi-cli --dry-run -i <name>`` and parses the expanded
command. The subprocess environment pins ``PI_CLI_CONFIG`` at the resolved file
so the user's config is never mutated (which ``-p/--path`` would do).
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .errors import (
    ConfigNotFoundError,
    ConfigParseError,
    PiAgentGraphError,
    PiCliNotFoundError,
    SavedConfigNotFoundError,
)

CONFIG_FILENAME = "config.json"

Runner = Callable[
    [Sequence[str], Mapping[str, str]], "subprocess.CompletedProcess[str]"
]


def default_config_dir() -> Path:
    """The pi-cli config directory, honoring the same env vars as pi-cli."""
    override = os.environ.get("PI_CLI_CONFIG_DIR")
    if override and override.strip():
        return Path(override)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg and xdg.strip() else Path.home() / ".config"
    return base / "pi-cli"


def _as_config_file(path: Path) -> Path:
    """Treat *path* as a file unless it clearly names a directory."""
    if path.is_dir():
        return path / CONFIG_FILENAME
    return path


def resolve_config_path(config_path: str | Path | None = None) -> Path:
    """Resolve the active config file path *without* following the ``path`` key."""
    if config_path is not None:
        return _as_config_file(Path(config_path))
    env = os.environ.get("PI_CLI_CONFIG")
    if env and env.strip():
        return _as_config_file(Path(env))
    return default_config_dir() / CONFIG_FILENAME


def _follow_path_pointer(path: Path) -> Path:
    """Honor the top-level ``path`` key written by ``pi-cli -p``."""
    if not path.exists():
        return path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return path
    if isinstance(data, dict):
        pointer = data.get("path")
        if isinstance(pointer, str) and pointer.strip():
            candidate = _as_config_file(Path(pointer))
            if candidate.exists():
                return candidate
    return path


def resolve_active_config(config_path: str | Path | None = None) -> Path:
    """Resolve the active config file, following the ``path`` pointer."""
    return _follow_path_pointer(resolve_config_path(config_path))


def _default_runner(
    argv: Sequence[str], env: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        env=dict(env),
        check=False,
    )


class ConfigLoader:
    """Reads saved agents from a pi-cli config and expands them to argv."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        pi_cli_bin: str = "pi-cli",
        runner: Runner | None = None,
    ) -> None:
        self.config_path = resolve_active_config(config_path)
        self.pi_cli_bin = pi_cli_bin
        self._runner = runner or _default_runner

    # -- reading ----------------------------------------------------------
    def _read_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise ConfigNotFoundError(f"pi-cli config not found: {self.config_path}")
        try:
            text = self.config_path.read_text(encoding="utf-8")
        except OSError as error:  # pragma: no cover - unusual IO failure
            raise ConfigNotFoundError(
                f"could not read pi-cli config: {self.config_path}"
            ) from error
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise ConfigParseError(
                f"invalid JSON in {self.config_path}: {error}"
            ) from error
        if not isinstance(data, dict):
            raise ConfigParseError(
                f"pi-cli config must be a JSON object: {self.config_path}"
            )
        return data

    def _agents(self) -> dict[str, Any]:
        agents = self._read_config().get("agents")
        if agents is None:
            return {}
        if not isinstance(agents, dict):
            raise ConfigParseError("pi-cli config 'agents' must be an object")
        return agents

    # -- public API -------------------------------------------------------
    def list(self) -> list[str]:
        """Return the saved agent names, in config order."""
        return list(self._agents())

    def get_raw(self, name: str) -> str:
        """Return the raw saved command string for *name*."""
        agents = self._agents()
        if name not in agents:
            available = ", ".join(sorted(agents)) or "<none>"
            raise SavedConfigNotFoundError(
                f"saved config not found: {name!r} (available: {available})"
            )
        value = agents[name]
        if not isinstance(value, str):
            raise ConfigParseError(f"saved config {name!r} must be a string")
        return value

    def _resolve_executable(self) -> str:
        found = shutil.which(self.pi_cli_bin)
        if found:
            return found
        candidate = Path(self.pi_cli_bin)
        if candidate.exists():
            return str(candidate)
        raise PiCliNotFoundError(
            f"could not find {self.pi_cli_bin!r} on PATH or as a path"
        )

    def get(self, name: str) -> Sequence[str]:
        """Expand a saved config name into a full ``pi`` argv list."""
        self.get_raw(name)  # validate existence first, with a clear error
        executable = self._resolve_executable()
        env = os.environ.copy()
        env["PI_CLI_CONFIG"] = str(self.config_path)
        argv = [executable, "--dry-run", "-i", name]
        proc = self._runner(argv, env)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise PiAgentGraphError(
                f"pi-cli failed for {name!r} (exit {proc.returncode}): {detail}"
            )
        return parse_dry_run(proc.stdout)


def parse_dry_run(output: str) -> list[str]:
    """Split ``pi-cli --dry-run`` stdout into an argv list."""
    text = output.strip()
    if not text:
        raise PiAgentGraphError("pi-cli --dry-run produced no output")
    return shlex.split(text, posix=True)
