"""Core data model: :class:`Agent`, :class:`Role`, and :class:`Scenario`.

The key invariant in this module is that an :class:`Agent` owns its managed
flags (``--name``, ``--session-dir``, ``--system-prompt``) as *fields*, never as
loose tokens in ``base_argv``. That makes system-prompt injection a replace
rather than an append, and keeps :meth:`Agent.build_argv` deterministic and
side-effect free.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

# Managed flag -> dataclass field name.
MANAGED_FLAGS: dict[str, str] = {
    "--name": "name",
    "--session-dir": "session_dir",
    "--system-prompt": "system_prompt",
}


def _split_managed(argv: Sequence[str]) -> tuple[dict[str, str], list[str]]:
    """Return ``(managed_values, remaining_argv)``.

    Recognizes both ``--flag value`` and ``--flag=value`` spellings. When a
    managed flag repeats, the last occurrence wins. A trailing flag with no
    value is dropped.
    """
    found: dict[str, str] = {}
    remaining: list[str] = []
    index = 0
    length = len(argv)
    while index < length:
        token = argv[index]
        attr: str | None = None
        value: str | None = None
        for flag, field_name in MANAGED_FLAGS.items():
            if token == flag:
                attr = field_name
                if index + 1 < length:
                    value = argv[index + 1]
                    index += 2
                else:
                    index += 1
                break
            if token.startswith(flag + "="):
                attr = field_name
                value = token[len(flag) + 1 :]
                index += 1
                break
        if attr is None:
            remaining.append(token)
            index += 1
            continue
        if value is not None:
            found[attr] = value
    return found, remaining


def _strip_flag(argv: Sequence[str], flag: str) -> list[str]:
    """Remove every ``flag value`` / ``flag=value`` occurrence from *argv*."""
    result: list[str] = []
    index = 0
    length = len(argv)
    while index < length:
        token = argv[index]
        if token == flag:
            index += 2  # drop the flag and its value
            continue
        if token.startswith(flag + "="):
            index += 1
            continue
        result.append(token)
        index += 1
    return result


@dataclass
class Agent:
    """A single pi session to be launched."""

    role: str
    base_argv: list[str] = field(default_factory=list)
    name: str | None = None
    session_dir: str | None = None
    system_prompt: str | None = None
    prompt: str | None = None
    cwd: str | None = None

    def __post_init__(self) -> None:
        if self.name is None:
            self.name = self.role

    # -- command ---------------------------------------------------------
    def set_command(self, argv: Sequence[str]) -> None:
        """Set the resolved ``pi`` command, extracting managed flags.

        Any ``--name`` / ``--session-dir`` / ``--system-prompt`` present in
        *argv* is lifted into its field; the rest stays in ``base_argv``.
        """
        self.base_argv = list(argv)
        found, remaining = _split_managed(self.base_argv)
        self.base_argv = remaining
        for field_name, value in found.items():
            setattr(self, field_name, value)

    def set_option(self, flag: str, value: str) -> None:
        """Set an option, replacing any existing occurrence.

        Managed flags route to their field; everything else is normalized in
        ``base_argv``.
        """
        if flag in MANAGED_FLAGS:
            setattr(self, MANAGED_FLAGS[flag], value)
            return
        self.base_argv = _strip_flag(self.base_argv, flag)
        self.base_argv += [flag, value]

    # -- individual setters ---------------------------------------------
    def set_name(self, name: str) -> None:
        self.name = name

    def set_session_dir(self, path: str) -> None:
        self.session_dir = path

    def set_system_prompt(self, text: str) -> None:
        self.system_prompt = text

    def set_prompt(self, text: str) -> None:
        self.prompt = text

    def set_cwd(self, path: str) -> None:
        self.cwd = path

    def set_dir(self, path: str) -> None:
        """Alias for :meth:`set_cwd`: the agent's working directory."""
        self.set_cwd(path)

    # -- rendering --------------------------------------------------------
    def build_argv(self) -> list[str]:
        """Return a fresh, fully-assembled argv. Never mutates ``self``."""
        _, argv = _split_managed(self.base_argv)
        if self.name:
            argv += ["--name", self.name]
        if self.session_dir:
            argv += ["--session-dir", self.session_dir]
        if self.system_prompt:
            argv += ["--system-prompt", self.system_prompt]
        if self.prompt:
            argv += ["--", self.prompt]
        return argv


@dataclass
class Role:
    """A logical function within a scenario."""

    name: str
    description: str = ""
    config: str | None = None


@dataclass
class Scenario:
    """A named multi-agent workflow template."""

    key: str
    description: str
    roles: dict[str, Role] = field(default_factory=dict)

    def agent_names(self) -> list[str]:
        return list(self.roles)

    def get(self, name: str) -> Role:
        return self.roles[name]
