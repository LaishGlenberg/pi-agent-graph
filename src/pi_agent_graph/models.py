"""Core data model: :class:`Agent`, :class:`Role`, and :class:`Scenario`.

The key invariant in this module is that an :class:`Agent` owns its managed
flags (``--name``, ``--session-dir``, ``--model``, ``--system-prompt``) and its
resource choices (extensions, skills, built-in tools, and the ``use_*``
switches) as *fields*, never as loose tokens in ``base_argv``. That makes
system-prompt injection and resource overrides a replace rather than an append,
and lets a Python-level choice override a config one, while keeping
:meth:`Agent.build_argv` deterministic and side-effect free.
"""

from __future__ import annotations

import json
import os
import shlex
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .resources import (
    BUILTIN_TOOLS,
    builtin_tool_flags,
    resolve_builtin_tools,
    resolve_extensions,
    resolve_skills,
)

# Managed flag -> dataclass field name.
MANAGED_FLAGS: dict[str, str] = {
    "--name": "name",
    "--session-dir": "session_dir",
    "--model": "model",
    "--system-prompt": "system_prompt",
}

#: How many trailing system-prompt characters :meth:`Agent.display_command` keeps.
SYSTEM_PROMPT_PREVIEW_CHARS = 30

#: pi-cli config-style resource flags :meth:`Agent.display_command` recognizes.
_EXTENSION_FLAGS = ("-e", "--extension")
_SKILL_FLAGS = ("-s", "--skill")
_EXCLUDE_TOOLS_FLAGS = ("-xt", "--exclude-tools")
_NO_EXTENSION_FLAGS = ("-ne", "--no-extensions")
_NO_SKILL_FLAGS = ("-ns", "--no-skills")
_NO_CONTEXT_FLAGS = ("-nc", "--no-context-files")
_NO_BUILTIN_TOOL_FLAGS = ("-nbt", "--no-builtin-tools")
_NO_TOOL_FLAGS = ("-nt", "--no-tools")
_RESOURCE_SUFFIXES = (".ts", ".js", ".mjs", ".cjs", ".md")

#: pi's valid thinking levels. Used to recognize a ``model:thinking`` suffix so
#: :meth:`Agent.set_model` can replace it instead of stacking a second ``:``.
THINKING_LEVELS: tuple[str, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


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


def _strip_value_option(
    argv: Sequence[str], long_flag: str, short_flag: str
) -> list[str]:
    """Remove ``--flag value``, ``--flag=value``, ``-f value``, and ``-fvalue``."""
    result: list[str] = []
    index = 0
    length = len(argv)
    while index < length:
        token = argv[index]
        if token in (long_flag, short_flag):
            index += 2  # drop the flag and its detached value
            continue
        if token.startswith(long_flag + "="):
            index += 1
            continue
        if token.startswith(short_flag) and len(token) > len(short_flag):
            index += 1  # attached value, with or without a leading `=`
            continue
        result.append(token)
        index += 1
    return result


def _strip_tokens(argv: Sequence[str], tokens: Sequence[str]) -> list[str]:
    """Remove every exact token in *tokens* from *argv*."""
    drop = set(tokens)
    return [token for token in argv if token not in drop]


def _default_pi_argv() -> list[str]:
    """The default command, mirroring pi-cli's ``PI_BIN || "pi"``."""
    return [os.environ.get("PI_BIN") or "pi"]


def _system_prompt_preview(text: str) -> str:
    """Return a double-quoted preview of the system prompt's tail."""
    if len(text) > SYSTEM_PROMPT_PREVIEW_CHARS:
        preview = "..." + text[-SYSTEM_PROMPT_PREVIEW_CHARS:]
    else:
        preview = text
    return json.dumps(preview, ensure_ascii=False)


def _resource_name(path: str) -> str:
    """Shorten a resolved resource path to the name a config would use."""
    name = Path(path).name
    for suffix in _RESOURCE_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _dedupe(values: Sequence[str]) -> list[str]:
    """Return *values* with duplicates removed, preserving order."""
    return list(dict.fromkeys(values))


def _kept_builtin_tools(excluded: str) -> list[str] | None:
    """Invert an ``--exclude-tools`` value into a ``-bt`` allowlist."""
    names = {name.strip() for name in excluded.split(",") if name.strip()}
    if not names or not names.issubset(BUILTIN_TOOLS):
        return None
    return [tool for tool in BUILTIN_TOOLS if tool not in names]


def _render_tokens(tokens: Sequence[str]) -> str:
    """Join *tokens*, quoting safely and abbreviating prompts."""
    rendered: list[str] = []
    index = 0
    length = len(tokens)
    while index < length:
        token = tokens[index]
        if token == "--system-prompt" and index + 1 < length:
            rendered.append(token)
            rendered.append(_system_prompt_preview(tokens[index + 1]))
            index += 2
            continue
        if token.startswith("--system-prompt="):
            rendered.append("--system-prompt")
            rendered.append(_system_prompt_preview(token.split("=", 1)[1]))
            index += 1
            continue
        if token == "--" and index + 1 < length:
            rendered.append(token)
            rendered.append(json.dumps(tokens[index + 1], ensure_ascii=False))
            index += 2
            continue
        rendered.append(shlex.quote(token))
        index += 1
    return " ".join(rendered)


def _format_command(
    argv: Sequence[str], *, builtin_tools: list[str] | None = None
) -> str:
    """Render a resolved ``pi`` argv in pi-cli config style.

    Resolved extension/skill paths are shortened back to their config names,
    resource and tool flags are merged, and the (usually multi-line) system
    prompt is abbreviated to a double-quoted tail so the line stays scannable.
    """
    extensions: list[str] = []
    skills: list[str] = []
    passthrough: list[str] = []
    excluded: str | None = None
    no_extensions = no_skills = no_context = no_builtin = no_tools = False

    index = 1
    length = len(argv)
    while index < length:
        token = argv[index]
        if token in _EXTENSION_FLAGS and index + 1 < length:
            extensions.append(argv[index + 1])
            index += 2
            continue
        if token.startswith("--extension="):
            extensions.append(token.split("=", 1)[1])
            index += 1
            continue
        if token in _SKILL_FLAGS and index + 1 < length:
            skills.append(argv[index + 1])
            index += 2
            continue
        if token.startswith("--skill="):
            skills.append(token.split("=", 1)[1])
            index += 1
            continue
        if token in _EXCLUDE_TOOLS_FLAGS and index + 1 < length:
            excluded = argv[index + 1]
            index += 2
            continue
        if token.startswith("--exclude-tools="):
            excluded = token.split("=", 1)[1]
            index += 1
            continue
        if token in _NO_EXTENSION_FLAGS:
            no_extensions = True
        elif token in _NO_SKILL_FLAGS:
            no_skills = True
        elif token in _NO_CONTEXT_FLAGS:
            no_context = True
        elif token in _NO_BUILTIN_TOOL_FLAGS:
            no_builtin = True
        elif token in _NO_TOOL_FLAGS:
            no_tools = True
        else:
            passthrough.append(token)
        index += 1

    parts = list(argv[:1])
    if no_extensions and not extensions:
        parts.append("-ne")
    if no_skills and not skills:
        parts.append("-ns")
    if skills:
        parts += ["-s", ",".join(_dedupe([_resource_name(s) for s in skills]))]
    if extensions:
        parts += ["-e", ",".join(_dedupe([_resource_name(e) for e in extensions]))]
    if builtin_tools:
        parts += ["-bt", ",".join(builtin_tools)]
    elif excluded is not None:
        allowed = _kept_builtin_tools(excluded)
        if allowed is not None and not no_builtin and not no_tools:
            parts += ["-nbt"] if not allowed else ["-bt", ",".join(allowed)]
        else:
            parts += ["--exclude-tools", excluded]
    if no_context:
        parts.append("-nc")
    if no_builtin:
        parts.append("-nbt")
    if no_tools:
        parts.append("-nt")
    parts += passthrough
    return _render_tokens(parts)


class Switch:
    """A Python-level on/off choice for one resource family.

    ``explicit`` distinguishes the untouched default (enabled) from a call to
    :meth:`set`, so builder defaults only fill agents that did not choose for
    themselves. ``get()`` returns the current value; setting it to ``True`` is
    a no-op unless a saved config disabled the family, in which case the
    config's disable flag is removed.
    """

    __slots__ = ("_enabled", "_explicit")

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._explicit = False

    def set(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self._explicit = True

    def get(self) -> bool:
        return self._enabled

    @property
    def explicit(self) -> bool:
        return self._explicit

    def __bool__(self) -> bool:
        return self._enabled

    def __repr__(self) -> str:
        return f"Switch(enabled={self._enabled!r}, explicit={self._explicit!r})"


@dataclass
class Agent:
    """A single pi session to be launched."""

    role: str
    base_argv: list[str] = field(default_factory=_default_pi_argv)
    name: str | None = None
    session_dir: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    prompt: str | None = None
    cwd: str | None = None
    #: Resolved extension paths chosen in Python. ``None`` means "leave whatever
    #: the saved command carries"; an empty list means "no extensions".
    extensions: list[str] | None = None
    skills: list[str] | None = None
    #: Built-in tools to keep; the rest are disabled via ``--exclude-tools``.
    builtin_tools: list[str] | None = None
    #: Optional agent directory for name resolution (defaults to pi's).
    agent_dir: str | None = None
    use_extensions: Switch = field(default_factory=Switch)
    use_skills: Switch = field(default_factory=Switch)
    use_tools: Switch = field(default_factory=Switch)
    use_context: Switch = field(default_factory=Switch)
    #: True when the model was chosen in Python (constructor or
    #: :meth:`set_model`) rather than inherited from the pi-cli config. A
    #: builder-level default only fills in agents whose model is *not*
    #: explicit, so per-agent choices always win.
    model_explicit: bool = False

    def __post_init__(self) -> None:
        if self.name is None:
            self.name = self.role
        if self.model is not None:
            self.model_explicit = True

    def __str__(self) -> str:
        return self.get_name()

    def get_name(self) -> str:
        """Return the agent's display name (defaults to its role)."""
        return self.name if self.name is not None else self.role

    # -- command ---------------------------------------------------------
    def set_command(self, argv: Sequence[str]) -> None:
        """Set the resolved ``pi`` command, extracting managed flags.

        Any ``--name`` / ``--session-dir`` / ``--model`` / ``--system-prompt``
        present in *argv* is lifted into its field; the rest stays in
        ``base_argv``.
        """
        self.base_argv = list(argv)
        found, remaining = _split_managed(self.base_argv)
        self.base_argv = remaining
        for field_name, value in found.items():
            setattr(self, field_name, value)
        if "model" in found:
            # A model carried by the saved command is the pi-cli default, not a
            # Python-level choice, so it never blocks a builder default.
            self.model_explicit = False

    def set_option(self, flag: str, value: str) -> None:
        """Set an option, replacing any existing occurrence.

        Managed flags route to their field; everything else is normalized in
        ``base_argv``.
        """
        if flag in MANAGED_FLAGS:
            setattr(self, MANAGED_FLAGS[flag], value)
            if flag == "--model":
                self.model_explicit = True
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

    def set_model(self, model: str, thinking: str | None = None) -> None:
        """Set the agent's model, overriding any pi-cli config value.

        ``thinking`` is appended as pi's ``model:thinking`` suffix. An existing
        thinking suffix on *model* is replaced rather than stacked, and a bare
        ``--thinking`` flag left in ``base_argv`` is removed so the chosen
        suffix is authoritative (``--thinking`` would otherwise override it).
        """
        if thinking:
            base = model
            head, separator, suffix = model.rpartition(":")
            if separator and suffix in THINKING_LEVELS:
                base = head
            self.model = f"{base}:{thinking}"
            self.base_argv = _strip_flag(self.base_argv, "--thinking")
        else:
            self.model = model
        self.model_explicit = True

    def set_prompt(self, text: str) -> None:
        self.prompt = text

    def set_cwd(self, path: str) -> None:
        self.cwd = path

    def set_dir(self, path: str) -> None:
        """Alias for :meth:`set_cwd`: the agent's working directory."""
        self.set_cwd(path)

    # -- resources --------------------------------------------------------
    def set_extensions(self, *names: str, agent_dir: str | Path | None = None) -> None:
        """Resolve extension names/paths and load exactly those extensions.

        Values may be repeated or comma-separated. Resolved paths replace any
        ``-e``/``-ne`` pair carried by the saved command, and any extension
        names already there. Calling with no names (or only empty strings) is
        equivalent to :meth:`Switch.set` ``False`` on ``use_extensions``.
        """
        resolved = resolve_extensions(names, agent_dir or self.agent_dir)
        if not resolved:
            self.extensions = []
            self.use_extensions.set(False)
            return
        self.extensions = resolved
        self.use_extensions.set(True)

    def set_skills(self, *names: str, agent_dir: str | Path | None = None) -> None:
        """Resolve skill names/paths and load exactly those skills.

        Values may be repeated or comma-separated. Resolved paths replace any
        ``--skill``/``-ns`` pair carried by the saved command. Calling with no
        names (or only empty strings) disables skills via ``use_skills``.
        """
        resolved = resolve_skills(names, agent_dir or self.agent_dir)
        if not resolved:
            self.skills = []
            self.use_skills.set(False)
            return
        self.skills = resolved
        self.use_skills.set(True)

    def set_tools(self, *names: str) -> None:
        """Keep only the named built-in tools, like pi-cli's ``-bt``.

        The rest become ``--exclude-tools`` while extension tools stay enabled.
        Calling with no names (or only empty strings) disables built-in tools
        via ``use_tools``.
        """
        tools = resolve_builtin_tools(names)
        if not tools:
            self.builtin_tools = []
            self.use_tools.set(False)
            return
        self.builtin_tools = tools
        self.use_tools.set(True)

    # -- rendering --------------------------------------------------------
    def _compose_resource_argv(self, argv: list[str]) -> list[str]:
        """Replace the saved command's resource flags with Python choices."""
        if self.extensions is not None or self.use_extensions.explicit:
            argv = _strip_value_option(argv, "--extension", "-e")
            argv = _strip_tokens(argv, ("-ne", "--no-extensions"))
            if not self.use_extensions.get():
                argv += ["-ne"]
            elif self.extensions:
                argv += ["-ne"]
                for path in self.extensions:
                    argv += ["--extension", path]

        if self.skills is not None or self.use_skills.explicit:
            argv = _strip_value_option(argv, "--skill", "-s")
            argv = _strip_tokens(argv, ("-ns", "--no-skills"))
            if not self.use_skills.get():
                argv += ["-ns"]
            elif self.skills:
                argv += ["-ns"]
                for path in self.skills:
                    argv += ["--skill", path]

        if self.builtin_tools is not None or self.use_tools.explicit:
            argv = _strip_value_option(argv, "--exclude-tools", "-xt")
            argv = _strip_tokens(
                argv, ("-nt", "--no-tools", "-nbt", "--no-builtin-tools")
            )
            if not self.use_tools.get():
                argv += ["-nbt"]
            elif self.builtin_tools is not None:
                argv += builtin_tool_flags(self.builtin_tools)

        if self.use_context.explicit:
            argv = _strip_tokens(argv, ("-nc", "--no-context-files"))
            if not self.use_context.get():
                argv += ["-nc"]

        return argv

    def build_argv(self) -> list[str]:
        """Return a fresh, fully-assembled argv. Never mutates ``self``."""
        _, argv = _split_managed(self.base_argv)
        argv = self._compose_resource_argv(argv)
        if self.name:
            argv += ["--name", self.name]
        if self.session_dir:
            argv += ["--session-dir", self.session_dir]
        if self.model:
            argv += ["--model", self.model]
        if self.system_prompt:
            argv += ["--system-prompt", self.system_prompt]
        if self.prompt:
            argv += ["--", self.prompt]
        return argv

    def display_command(self) -> str:
        """Return a readable, pi-cli-config-style command line for this agent."""
        return _format_command(self.build_argv(), builtin_tools=self.builtin_tools)


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
