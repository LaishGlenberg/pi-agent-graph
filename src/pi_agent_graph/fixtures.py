"""Scenario fixtures: serializable definitions that can be saved and reloaded.

A fixture captures the pieces of a scenario that a user typically tunes — the
shared context, the shared goal, the per-role pi-cli command names, and each
role's starting prompt — behind a stable ``identifier``. Fixtures round-trip to
and from JSON on disk so a scenario can be rebuilt without re-entering all the
fields by hand.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .errors import FixtureError, FixtureFormatError, FixtureNotFoundError

DEFAULT_FIXTURE_DIR = Path("fixtures")


def validate_identifier(identifier: object) -> str:
    """Return *identifier* if it is a safe, non-empty file stem.

    Rejects non-strings, blank strings, and anything containing a path
    separator (so a fixture identifier can never escape its directory).
    """
    if not isinstance(identifier, str) or not identifier.strip():
        raise FixtureFormatError("fixture 'identifier' must be a non-empty string")
    if any(sep in identifier for sep in ("/", "\\")) or identifier in (".", ".."):
        raise FixtureFormatError(
            f"fixture identifier {identifier!r} must not contain path separators"
        )
    return identifier


def _optional_str(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise FixtureFormatError(f"{label} must be a string or null")
    return value


def _text_field(data: Mapping[str, object], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise FixtureFormatError(f"fixture {key!r} must be a string")
    return value


def _required_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FixtureFormatError(f"fixture {key!r} must be a non-empty string")
    return value


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

    def to_dict(self) -> dict[str, str | None]:
        return {"config": self.config, "prompt": self.prompt, "name": self.name}

    @classmethod
    def from_dict(cls, data: object) -> RoleFixture:
        if not isinstance(data, dict):
            raise FixtureFormatError("role fixture must be a mapping")
        return cls(
            config=_optional_str(data.get("config"), "role fixture 'config'"),
            prompt=_optional_str(data.get("prompt"), "role fixture 'prompt'"),
            name=_optional_str(data.get("name"), "role fixture 'name'"),
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
        self.identifier = validate_identifier(self.identifier)
        if not isinstance(self.scenario, str) or not self.scenario.strip():
            raise FixtureFormatError("fixture 'scenario' must be a non-empty string")

    def to_dict(self) -> dict[str, object]:
        return {
            "identifier": self.identifier,
            "scenario": self.scenario,
            "shared_goal": self.shared_goal,
            "shared_context": self.shared_context,
            "roles": {key: value.to_dict() for key, value in self.roles.items()},
        }

    @classmethod
    def from_dict(cls, data: object) -> ScenarioFixture:
        if not isinstance(data, dict):
            raise FixtureFormatError("fixture must be a mapping")
        raw_roles = data.get("roles") or {}
        if not isinstance(raw_roles, dict):
            raise FixtureFormatError("fixture 'roles' must be a mapping")
        roles = {key: RoleFixture.from_dict(value) for key, value in raw_roles.items()}
        return cls(
            identifier=_required_str(data, "identifier"),
            scenario=_required_str(data, "scenario"),
            shared_goal=_text_field(data, "shared_goal"),
            shared_context=_text_field(data, "shared_context"),
            roles=roles,
        )


def fixture_path(identifier: str, directory: str | Path | None = None) -> Path:
    """Return ``<directory or 'fixtures'>/<identifier>.json``."""
    base = Path(directory) if directory is not None else DEFAULT_FIXTURE_DIR
    return base / f"{validate_identifier(identifier)}.json"


def save_fixture(fixture: ScenarioFixture, path: str | Path) -> Path:
    """Serialize *fixture* to JSON at *path*, creating parents as needed.

    Raises :class:`FixtureError` if the file cannot be written.
    """
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(fixture.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise FixtureError(f"could not write fixture {target}: {exc}") from exc
    return target


def load_fixture(path: str | Path) -> ScenarioFixture:
    """Load a :class:`ScenarioFixture` from JSON at *path*.

    Raises :class:`FixtureNotFoundError` when the file is missing,
    :class:`FixtureFormatError` on invalid JSON or schema, and
    :class:`FixtureError` on other I/O failures.
    """
    source = Path(path)
    if not source.exists():
        raise FixtureNotFoundError(f"fixture file not found: {source}")
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise FixtureError(f"could not read fixture {source}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FixtureFormatError(f"fixture is not valid JSON: {source}: {exc}") from exc
    return ScenarioFixture.from_dict(data)
