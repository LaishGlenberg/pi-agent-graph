"""Tests for the Python port of pi-cli's resource resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

import pi_agent_graph.resources as resources
from pi_agent_graph.errors import (
    AmbiguousResourceError,
    ResourceNotFoundError,
    UnknownToolError,
)
from pi_agent_graph.resources import (
    BUILTIN_TOOLS,
    builtin_tool_flags,
    default_agent_dir,
    excluded_builtin_tools,
    normalize_names,
    resolve_builtin_tools,
    resolve_extension,
    resolve_extensions,
    resolve_skill,
    resolve_skills,
    walk_entries,
)


def write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def npm_package(
    agent_dir: Path,
    directory_name: str,
    package_name: str | None = None,
) -> Path:
    """Create an npm-installed pi extension and return its directory."""
    package_dir = agent_dir / "npm" / "node_modules" / directory_name
    write(
        package_dir / "package.json",
        f'{{"name": "{package_name or directory_name}", "pi": {{}}}}',
    )
    write(package_dir / "index.ts")
    return package_dir


def local_extension(agent_dir: Path, name: str) -> Path:
    return write(agent_dir / "extensions" / name / "index.ts").parent


# -- agent dir -------------------------------------------------------------
def test_default_agent_dir_prefers_pi_agent_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PI_AGENT_DIR", str(tmp_path))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "other"))
    assert default_agent_dir() == tmp_path


def test_default_agent_dir_falls_back_to_coding_agent_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("PI_AGENT_DIR", raising=False)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    assert default_agent_dir() == tmp_path


def test_default_agent_dir_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("PI_AGENT_DIR", raising=False)
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    assert default_agent_dir() == resources.DEFAULT_AGENT_DIR


# -- walking ---------------------------------------------------------------
def test_walk_skips_dependency_and_git_directories(tmp_path):
    write(tmp_path / "keep.txt")
    write(tmp_path / "node_modules" / "skip.txt")
    write(tmp_path / ".git" / "skip.txt")
    write(tmp_path / "sub" / "nested.txt")

    names = {entry.name for entry in walk_entries(tmp_path)}

    assert "keep.txt" in names
    assert "nested.txt" in names
    assert "skip.txt" not in names


def test_walk_records_depth_and_respects_max_depth(tmp_path):
    write(tmp_path / "one" / "two" / "three.txt")

    shallow = list(walk_entries(tmp_path, max_depth=1))
    assert [entry.name for entry in shallow] == ["one"]

    deep = [entry for entry in walk_entries(tmp_path) if entry.name == "three.txt"]
    assert deep[0].depth == 3


# -- extensions ------------------------------------------------------------
def test_resolve_extension_explicit_path_passes_through(tmp_path):
    extension = local_extension(tmp_path / "agent", "local")
    assert resolve_extension(str(extension), tmp_path / "agent") == str(extension)


def test_resolve_extension_from_npm(tmp_path):
    agent_dir = tmp_path / "agent"
    package_dir = npm_package(agent_dir, "pi-intercom")

    assert resolve_extension("pi-intercom", agent_dir) == str(package_dir.resolve())


def test_resolve_extension_matches_scoped_package_name(tmp_path):
    agent_dir = tmp_path / "agent"
    package_dir = npm_package(agent_dir, "@scope/pi-intercom")
    # The folder name matches the unscoped request.
    assert resolve_extension("pi-intercom", agent_dir) == str(package_dir.resolve())
    # The full package name also matches through package.json metadata.
    assert resolve_extension("@scope/pi-intercom", agent_dir) == str(
        package_dir.resolve()
    )


def test_resolve_extension_from_git_source_file(tmp_path):
    agent_dir = tmp_path / "agent"
    source = write(agent_dir / "git" / "orca-prefill.ts")

    assert resolve_extension("orca-prefill", agent_dir) == str(source.resolve())


def test_resolve_extension_from_local_extensions_tree(tmp_path):
    agent_dir = tmp_path / "agent"
    extension = local_extension(agent_dir, "my-ext")

    assert resolve_extension("my-ext", agent_dir) == str(extension.resolve())


def test_resolve_extension_not_found(tmp_path):
    with pytest.raises(ResourceNotFoundError) as exc:
        resolve_extension("missing", tmp_path / "agent")
    message = str(exc.value)
    assert "extension not found: missing" in message
    assert "npm/node_modules" in message


def test_resolve_extension_ambiguous(tmp_path):
    agent_dir = tmp_path / "agent"
    write(agent_dir / "git" / "dup" / "index.ts")
    write(agent_dir / "extensions" / "dup" / "index.ts")

    with pytest.raises(AmbiguousResourceError) as exc:
        resolve_extension("dup", agent_dir)
    assert "ambiguous" in str(exc.value)


def test_resolve_extension_requires_a_name(tmp_path):
    with pytest.raises(ResourceNotFoundError):
        resolve_extension("", tmp_path)


# -- skills ----------------------------------------------------------------
def test_resolve_skill_file(tmp_path):
    agent_dir = tmp_path / "agent"
    skill = write(agent_dir / "skills" / "playwright-cli.md")

    assert resolve_skill("playwright-cli", agent_dir) == str(skill.resolve())


def test_resolve_skill_directory_with_skill_md(tmp_path):
    agent_dir = tmp_path / "agent"
    skill_dir = agent_dir / "skills" / "reviewer"
    write(skill_dir / "SKILL.md")

    assert resolve_skill("reviewer", agent_dir) == str(skill_dir.resolve())


def test_resolve_skill_inside_extension(tmp_path):
    agent_dir = tmp_path / "agent"
    skill_dir = agent_dir / "npm" / "node_modules" / "pi-intercom" / "skills" / "x"
    write(skill_dir / "SKILL.md")

    assert resolve_skill("x", agent_dir) == str(skill_dir.resolve())


def test_resolve_skill_ignores_directory_without_skill_md(tmp_path):
    agent_dir = tmp_path / "agent"
    write(agent_dir / "skills" / "not-a-skill" / "README.md")

    with pytest.raises(ResourceNotFoundError):
        resolve_skill("not-a-skill", agent_dir)


def test_resolve_skill_not_found(tmp_path):
    with pytest.raises(ResourceNotFoundError) as exc:
        resolve_skill("missing", tmp_path / "agent")
    assert "skill not found: missing" in str(exc.value)


# -- names + built-in tools ------------------------------------------------
def test_normalize_names_splits_and_trims():
    assert normalize_names(["a, b", "c", " ", ""]) == ["a", "b", "c"]


def test_resolve_extensions_and_skills(tmp_path):
    agent_dir = tmp_path / "agent"
    npm_package(agent_dir, "one")
    npm_package(agent_dir, "two")
    write(agent_dir / "skills" / "s1.md")
    write(agent_dir / "skills" / "s2.md")

    assert len(resolve_extensions(["one, two"], agent_dir)) == 2
    assert len(resolve_skills(["s1, s2"], agent_dir)) == 2


def test_resolve_builtin_tools_dedupes():
    assert resolve_builtin_tools(["read, bash", "read"]) == ["read", "bash"]


def test_resolve_builtin_tools_rejects_unknown():
    with pytest.raises(UnknownToolError) as exc:
        resolve_builtin_tools(["read", "nope"])
    assert "unknown built-in tool: nope" in str(exc.value)
    assert "read" in str(exc.value)


def test_builtin_tool_flags_excludes_the_rest():
    flags = builtin_tool_flags(["read", "bash"])
    assert flags[0] == "--exclude-tools"
    excluded = flags[1].split(",")
    assert set(excluded) == set(BUILTIN_TOOLS) - {"read", "bash"}


def test_builtin_tool_flags_empty_when_all_selected():
    assert builtin_tool_flags(list(BUILTIN_TOOLS)) == []


def test_excluded_builtin_tools_returns_the_rest():
    excluded = excluded_builtin_tools(["read", "bash"])
    assert set(excluded) == set(BUILTIN_TOOLS) - {"read", "bash"}


def test_excluded_builtin_tools_empty_when_all_selected():
    assert excluded_builtin_tools(list(BUILTIN_TOOLS)) == []
