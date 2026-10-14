"""Preflight validation. Nothing is launched unless every check passes."""

from __future__ import annotations

from ..errors import ValidationError
from ..models import Agent
from .types import LaunchOptions

#: Flags that are ambiguous between ``pi`` and ``pi-cli`` (or that would make a
#: session non-interactive). Generated commands must use the long form.
BANNED_FLAGS: tuple[str, ...] = ("-p", "-n", "--print")

KNOWN_BACKENDS: tuple[str, ...] = ("print", "bash", "terminal")


def validate(agents: list[Agent], backend: str, options: LaunchOptions) -> None:
    """Raise :class:`ValidationError` describing *all* problems found."""
    errors: list[str] = []

    if not agents:
        errors.append("no agents to launch")

    names: dict[str, list[str]] = {}
    for agent in agents:
        if not agent.base_argv:
            errors.append(f"agent {agent.role!r} has no command")
        name = agent.name or agent.role
        names.setdefault(name, []).append(agent.role)
        for token in agent.build_argv():
            if token in BANNED_FLAGS:
                errors.append(
                    f"agent {agent.role!r} uses ambiguous flag {token!r}; "
                    "use the long form"
                )

    for name, roles in names.items():
        if len(roles) > 1:
            errors.append(f"duplicate session name {name!r} used by roles {roles}")

    if backend not in KNOWN_BACKENDS:
        errors.append(
            f"unknown backend {backend!r} (known: {', '.join(KNOWN_BACKENDS)})"
        )

    if backend == "bash" and not options.bash_path:
        errors.append("backend 'bash' requires options.bash_path")

    if errors:
        raise ValidationError("preflight failed:\n- " + "\n- ".join(errors))
