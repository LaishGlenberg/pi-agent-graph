"""Tests for preflight validation."""

from __future__ import annotations

import pytest

from pi_agent_graph.errors import ValidationError
from pi_agent_graph.launchers.types import LaunchOptions
from pi_agent_graph.launchers.validation import (
    BANNED_FLAGS,
    KNOWN_BACKENDS,
    validate,
)
from pi_agent_graph.models import Agent


def make(role: str = "worker", argv=("pi",), **kwargs) -> Agent:
    agent = Agent(role=role, **kwargs)
    agent.set_command(list(argv))
    return agent


def opts(**kwargs) -> LaunchOptions:
    return LaunchOptions(**kwargs)


def test_valid_roster_passes():
    validate([make()], "print", opts())


@pytest.mark.parametrize("backend", KNOWN_BACKENDS)
def test_known_backends_accepted(backend):
    options = opts(bash_path="/tmp/x.sh") if backend == "bash" else opts()
    validate([make()], backend, options)


def test_empty_roster():
    with pytest.raises(ValidationError) as exc:
        validate([], "print", opts())
    assert "no agents" in str(exc.value)


def test_agent_without_command():
    with pytest.raises(ValidationError) as exc:
        validate([Agent(role="worker")], "print", opts())
    assert "no command" in str(exc.value)


def test_duplicate_names():
    first = make(role="worker", name="same")
    second = make(role="other", name="same")
    with pytest.raises(ValidationError) as exc:
        validate([first, second], "print", opts())
    assert "duplicate session name" in str(exc.value)


def test_duplicate_names_by_default_role():
    with pytest.raises(ValidationError):
        validate([make("worker"), make("worker")], "print", opts())


@pytest.mark.parametrize("flag", BANNED_FLAGS)
def test_banned_flags_rejected(flag):
    agent = Agent(role="worker")
    agent.set_command(["pi", flag, "x"])
    with pytest.raises(ValidationError):
        validate([agent], "print", opts())


@pytest.mark.parametrize("allowed", ["-ne", "-ns", "-nbt", "-np", "-nc"])
def test_allowed_dash_n_variants(allowed):
    validate([make(argv=["pi", allowed])], "print", opts())


def test_unknown_backend():
    with pytest.raises(ValidationError) as exc:
        validate([make()], "wat", opts())
    assert "unknown backend" in str(exc.value)


def test_bash_requires_path():
    with pytest.raises(ValidationError) as exc:
        validate([make()], "bash", opts())
    assert "bash_path" in str(exc.value)


def test_bash_with_path_passes():
    validate([make()], "bash", opts(bash_path="/tmp/x.sh"))


def test_multiple_errors_are_aggregated():
    with pytest.raises(ValidationError) as exc:
        validate([Agent(role="a"), Agent(role="b")], "npm", opts())
    message = str(exc.value)
    assert "no command" in message
    assert "unknown backend" in message
