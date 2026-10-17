"""Python port of pi-cli's extension/skill/tool resolution.

pi-cli lets saved commands refer to extensions and skills by name
(``-e pi-intercom``, ``-s playwright-cli``) and expands them to absolute paths
before running ``pi``. This module mirrors that logic so an :class:`Agent` can
be built entirely in Python, with no ``pi-cli`` subprocess.

Search order and matching rules are deliberately identical to pi-cli:

* extensions: ``$PI_AGENT_DIR/npm/node_modules`` (max depth 3, scoped packages
  at depth 2), then ``$PI_AGENT_DIR/git``, then ``$PI_AGENT_DIR/extensions``;
* skills: ``$PI_AGENT_DIR/skills`` first, then skills shipped inside the
  extension trees (a directory only counts when it holds a ``SKILL.md``);
* built-in tools: naming tools keeps only those and disables the rest through
  ``--exclude-tools``, leaving extension tools untouched.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import (
    AmbiguousResourceError,
    ResourceNotFoundError,
    UnknownToolError,
)

SOURCE_EXTENSIONS: tuple[str, ...] = (".ts", ".tsx", ".js", ".mjs", ".cjs")

#: Built-in tools pi can enable. Naming a subset with ``set_tools`` disables the
#: rest via ``--exclude-tools``.
BUILTIN_TOOLS: tuple[str, ...] = (
    "read",
    "bash",
    "powershell",
    "edit",
    "write",
    "grep",
    "find",
    "ls",
)

SKIPPED_DIRECTORIES: frozenset[str] = frozenset({"node_modules", ".git"})

DEFAULT_AGENT_DIR = Path.home() / ".pi" / "agent"


def default_agent_dir() -> Path:
    """Resolve pi's agent directory, honoring the same env vars as pi-cli.

    ``PI_AGENT_DIR`` is pi-cli's historical override; ``PI_CODING_AGENT_DIR`` is
    the variable pi itself documents, so it is honored as a fallback.
    """
    override = os.environ.get("PI_AGENT_DIR") or os.environ.get("PI_CODING_AGENT_DIR")
    if override and override.strip():
        return Path(override)
    return DEFAULT_AGENT_DIR


@dataclass(frozen=True)
class WalkEntry:
    """A single entry yielded while walking a directory tree."""

    path: Path
    name: str
    is_directory: bool
    depth: int


def walk_entries(
    root: str | Path,
    *,
    max_depth: int | None = None,
    skip_directories: frozenset[str] = SKIPPED_DIRECTORIES,
) -> Iterator[WalkEntry]:
    """Walk *root* without following dependency trees or git metadata.

    ``max_depth`` is measured from *root* (root itself is depth zero). Symlinked
    directories are followed once; broken links are ignored, and already-visited
    real paths are never revisited.
    """
    root_path = Path(root)
    if not root_path.exists():
        return
    visited: set[str] = set()
    yield from _visit(root_path, 0, max_depth, skip_directories, visited)


def _visit(
    directory: Path,
    depth: int,
    max_depth: int | None,
    skip_directories: frozenset[str],
    visited: set[str],
) -> Iterator[WalkEntry]:
    try:
        real_directory = directory.resolve(strict=True)
    except (OSError, RuntimeError):
        return
    key = str(real_directory)
    if key in visited:
        return
    visited.add(key)

    try:
        entries = sorted(directory.iterdir(), key=lambda path: path.name)
    except OSError:
        return

    for path in entries:
        try:
            is_directory = path.is_dir()
        except OSError:
            is_directory = False
        entry_depth = depth + 1
        yield WalkEntry(
            path=path,
            name=path.name,
            is_directory=is_directory,
            depth=entry_depth,
        )
        if (
            is_directory
            and (max_depth is None or entry_depth < max_depth)
            and path.name not in skip_directories
        ):
            yield from _visit(path, entry_depth, max_depth, skip_directories, visited)


def canonical_path(path: str | Path) -> str:
    """Resolve *path* when possible, falling back to an absolute path."""
    try:
        return str(Path(path).resolve(strict=True))
    except (OSError, RuntimeError):
        return str(Path(path).resolve())


def add_match(matches: list[str], path: str | Path) -> None:
    """Append the canonical form of *path* unless it is already recorded."""
    candidate = canonical_path(path)
    if candidate not in matches:
        matches.append(candidate)


def source_name_matches(filename: str, requested: str) -> bool:
    return filename == requested or any(
        filename == f"{requested}{extension}" for extension in SOURCE_EXTENSIONS
    )


def skill_file_matches(filename: str, requested: str) -> bool:
    return filename == requested or filename == f"{requested}.md"


def has_skill_file(directory: str | Path) -> bool:
    return (Path(directory) / "SKILL.md").is_file()


def add_skill_match(matches: list[str], path: str | Path) -> None:
    if has_skill_file(path):
        add_match(matches, path)


def read_package_json(directory: str | Path) -> dict[str, Any] | None:
    try:
        data = json.loads((Path(directory) / "package.json").read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def is_pi_package(package_json: dict[str, Any] | None) -> bool:
    return package_json is not None and package_json.get("pi") is not None


def has_extension_source(directory: str | Path) -> bool:
    return any(
        not entry.is_directory and entry.path.suffix in SOURCE_EXTENSIONS
        for entry in walk_entries(directory)
    )


def looks_like_extension_directory(directory: str | Path) -> bool:
    return is_pi_package(read_package_json(directory)) or has_extension_source(
        directory
    )


def package_name_matches(package_json: dict[str, Any] | None, requested: str) -> bool:
    if not package_json:
        return False
    name = package_json.get("name")
    if not isinstance(name, str):
        return False
    return name == requested or name.split("/")[-1] == requested


def _search_roots(agent_dir: str | Path) -> list[tuple[Path, str]]:
    base = Path(agent_dir)
    return [
        (base / "npm" / "node_modules", "npm"),
        (base / "git", "git"),
        (base / "extensions", "extensions"),
    ]


def resolve_extension(requested: str, agent_dir: str | Path | None = None) -> str:
    """Resolve an extension name to the path pi expects.

    Explicit paths (including paths outside the agent directory) pass through.
    Raises :class:`ResourceNotFoundError` or :class:`AmbiguousResourceError`.
    """
    if not requested:
        raise ResourceNotFoundError("--extension requires an extension name or path")

    if Path(requested).exists():
        return requested

    directory = Path(agent_dir) if agent_dir is not None else default_agent_dir()
    matches: list[str] = []

    for root, kind in _search_roots(directory):
        if not root.exists():
            continue
        is_npm = kind == "npm"

        # npm packages live at depth one, or depth two for scoped packages.
        # git and local extension trees may nest arbitrarily, and source files
        # (for example extensions/orca-prefill.ts) are valid matches too.
        for entry in walk_entries(root, max_depth=3 if is_npm else None):
            if entry.is_directory:
                if (
                    entry.name == requested
                    and (not is_npm or entry.depth <= 2)
                    and looks_like_extension_directory(entry.path)
                ):
                    add_match(matches, entry.path)
                continue

            if not is_npm and source_name_matches(entry.name, requested):
                add_match(matches, entry.path)

            # A package's directory name is not always its package name,
            # especially for scoped npm packages and git checkouts.
            if entry.name == "package.json":
                package_dir = entry.path.parent
                package_json = read_package_json(package_dir)
                if package_name_matches(package_json, requested) and is_pi_package(
                    package_json
                ):
                    add_match(matches, package_dir)

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ResourceNotFoundError(
            f"extension not found: {requested}\n"
            f"searched {directory}/npm/node_modules, {directory}/git, "
            f"and {directory}/extensions"
        )
    raise AmbiguousResourceError(
        f"extension name is ambiguous: {requested}\n"
        + "\n".join(f"  {match}" for match in matches)
        + "\nuse an explicit extension path to disambiguate"
    )


def resolve_skill(requested: str, agent_dir: str | Path | None = None) -> str:
    """Resolve a skill name to a file or skill directory pi accepts.

    Global skills are searched first, then skills shipped alongside extensions.
    Raises :class:`ResourceNotFoundError` or :class:`AmbiguousResourceError`.
    """
    if not requested:
        raise ResourceNotFoundError("--skill requires a skill name or path")

    if Path(requested).exists():
        return requested

    directory = Path(agent_dir) if agent_dir is not None else default_agent_dir()
    matches: list[str] = []

    global_skills = directory / "skills"
    if global_skills.exists():
        for entry in walk_entries(global_skills):
            if entry.is_directory:
                if entry.name == requested:
                    add_skill_match(matches, entry.path)
            elif skill_file_matches(entry.name, requested):
                add_match(matches, entry.path)

    for root, _kind in _search_roots(directory):
        if not root.exists():
            continue
        # SKILL.md is the marker for a skill directory, so an ordinary source
        # directory inside an extension is not mistaken for a skill.
        for entry in walk_entries(root):
            if entry.is_directory:
                if entry.name == requested:
                    add_skill_match(matches, entry.path)
            elif skill_file_matches(entry.name, requested):
                add_match(matches, entry.path)

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ResourceNotFoundError(
            f"skill not found: {requested}\n"
            f"searched {directory}/skills and skills inside "
            f"{directory}/npm/node_modules, {directory}/git, "
            f"and {directory}/extensions"
        )
    raise AmbiguousResourceError(
        f"skill name is ambiguous: {requested}\n"
        + "\n".join(f"  {match}" for match in matches)
        + "\nuse an explicit skill path to disambiguate"
    )


def normalize_names(values: Sequence[str]) -> list[str]:
    """Split comma-separated values and drop blanks, like pi-cli's `-e`/`-s`."""
    names: list[str] = []
    for value in values:
        for part in value.split(","):
            name = part.strip()
            if name:
                names.append(name)
    return names


def resolve_extensions(
    values: Sequence[str], agent_dir: str | Path | None = None
) -> list[str]:
    """Resolve every comma-separated extension name in *values*."""
    return [resolve_extension(name, agent_dir) for name in normalize_names(values)]


def resolve_skills(
    values: Sequence[str], agent_dir: str | Path | None = None
) -> list[str]:
    """Resolve every comma-separated skill name in *values*."""
    return [resolve_skill(name, agent_dir) for name in normalize_names(values)]


def resolve_builtin_tools(values: Sequence[str]) -> list[str]:
    """Validate built-in tool names, preserving order and dropping duplicates."""
    tools: list[str] = []
    for name in normalize_names(values):
        if name not in BUILTIN_TOOLS:
            raise UnknownToolError(
                f"unknown built-in tool: {name}\n"
                f"valid tools: {', '.join(BUILTIN_TOOLS)}"
            )
        if name not in tools:
            tools.append(name)
    return tools


def excluded_builtin_tools(tools: Sequence[str]) -> list[str]:
    """Return the built-in tools *not* named in *tools*, in canonical order."""
    selected = set(resolve_builtin_tools(tools))
    return [name for name in BUILTIN_TOOLS if name not in selected]


def builtin_tool_flags(tools: Sequence[str]) -> list[str]:
    """Expand selected built-in tools into pi's ``--exclude-tools`` flag."""
    excluded = excluded_builtin_tools(tools)
    if not excluded:
        return []
    return ["--exclude-tools", ",".join(excluded)]
