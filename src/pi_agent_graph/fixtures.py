"""Scenario fixtures: serializable definitions that can be saved and reloaded.

A fixture captures the pieces of a scenario that a user typically tunes — the
shared context, the shared goal, the per-role pi-cli command names, and each
role's starting prompt — behind a stable ``identifier``. Fixtures round-trip to
and from JSON on disk so a scenario can be rebuilt without re-entering all the
fields by hand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .errors import FixtureFormatError, FixtureNotFoundError

DEFAULT_FIXTURE_DIR = Path("fixtures")


@dataclass
class RoleFixture:
    """Per-role fixture data.

    ``config`` is the pi-cli command name (e.g. ``"planner_example"``) that
    resolves to this role's agent config, ``prompt`` is that agent's starting
    prompt, and ``name`` optionally overrides the agent's display name.
    """

    config: str | None = None
    prompt: str | None = None
    name: str | None = None

    def to_dict(self) -> dict:
        return {"config": self.config, "prompt": self.prompt, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> RoleFixture:
        if not isinstance(data, dict):
            raise FixtureFormatError("role fixture must be a mapping")
        return cls(
            config=data.get("config"),
            prompt=data.get("prompt"),
            name=data.get("name"),
        )


@dataclass
class ScenarioFixture:
    """A serializable scenario definition keyed by a stable ``identifier``."""

    identifier: str
    scenario: str
    shared_goal: str = ""
    shared_context: str = ""
    roles: dict[str, RoleFixture] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.identifier or not str(self.identifier).strip():
            raise FixtureFormatError("fixture 'identifier' must be a non-empty string")
        if not self.scenario or not str(self.scenario).strip():
            raise FixtureFormatError("fixture 'scenario' must be a non-empty string")

    def to_dict(self) -> dict:
        return {
            "identifier": self.identifier,
            "scenario": self.scenario,
            "shared_goal": self.shared_goal,
            "shared_context": self.shared_context,
            "roles": {key: value.to_dict() for key, value in self.roles.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScenarioFixture:
        if not isinstance(data, dict):
            raise FixtureFormatError("fixture must be a mapping")
        identifier = data.get("identifier")
        if not identifier or not str(identifier).strip():
            raise FixtureFormatError("fixture is missing a non-empty 'identifier'")
        scenario = data.get("scenario")
        if not scenario or not str(scenario).strip():
            raise FixtureFormatError("fixture is missing a non-empty 'scenario'")
        raw_roles = data.get("roles") or {}
        if not isinstance(raw_roles, dict):
            raise FixtureFormatError("fixture 'roles' must be a mapping")
        roles = {key: RoleFixture.from_dict(value) for key, value in raw_roles.items()}
        return cls(
            identifier=identifier,
            scenario=scenario,
            shared_goal=data.get("shared_goal", ""),
            shared_context=data.get("shared_context", ""),
            roles=roles,
        )


def fixture_path(identifier: str, directory: str | Path | None = None) -> Path:
    """Return ``<directory or 'fixtures'>/<identifier>.json``."""
    base = Path(directory) if directory is not None else DEFAULT_FIXTURE_DIR
    return base / f"{identifier}.json"


def save_fixture(fixture: ScenarioFixture, path: str | Path) -> Path:
    """Serialize *fixture* to JSON at *path*, creating parents as needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(fixture.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    return target


def load_fixture(path: str | Path) -> ScenarioFixture:
    """Load a :class:`ScenarioFixture` from JSON at *path*.

    Raises :class:`FixtureNotFoundError` when the file is missing and
    :class:`FixtureFormatError` on invalid JSON or schema.
    """
    source = Path(path)
    if not source.exists():
        raise FixtureNotFoundError(f"fixture file not found: {source}")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureFormatError(f"fixture is not valid JSON: {source}: {exc}") from exc
    return ScenarioFixture.from_dict(data)
