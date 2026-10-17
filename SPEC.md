# pi-agent-graph — Specification

Status: **draft / v1**. This document is the source of truth for the design.
The [README](./README.md) is the friendly overview; this file is the contract.

---

## 1. Purpose

`pi-agent-graph` is a Python library for describing and launching multi-agent
**pi** coding-agent workflows.

It does three things:

1. **Build agents** — a role, a resolved `pi` command, a session name, and an
   optional starting prompt.
2. **Resolve commands** from a user's saved [`pi-command-cli`] configuration, so
   extensions, skills, models, and system prompts come from config instead of
   hand-typed paths.
3. **Launch** each agent in its own terminal window, where agents coordinate
   over `pi-intercom`.

The value is turning a hand-written set of `pi-cli ...` invocations into a
declarative roster that is reproducible, testable, and cross-platform.

[`pi-command-cli`]: https://github.com/LaishGlenberg/pi-command-cli

## 2. Scope

### In scope (v1)

- Define agents as a roster (role, resolved `pi` command, name, optional prompt).
- Load saved `pi-cli` agent configs by name.
- Predefined **scenarios** (role prompts + a scenario description) defined in code.
- Shared goal / shared context prompt templating.
- Launch agents in new terminal windows on Windows, macOS, and Linux.
- Emit a reproducible shell script (`.sh` on POSIX, `.cmd` on Windows).
- A `print` backend for dry-runs and tests.

### Out of scope (v1)

- True graph orchestration (explicit edges / DAG / fan-out + fan-in).
- Capturing or streaming agent output.
- Auto-probing intercom readiness beyond launch ordering and a stagger delay.
- External scenario definition files (scenarios are code for now).
- A user-facing CLI (the `pi-agent-graph` entry point is reserved, see §14).
- Remote / distributed launching.

## 3. Terminology

| Term | Meaning |
| --- | --- |
| **Agent** | One `pi` session: role, `argv`, name, optional prompt. |
| **Role** | Logical function in a scenario, e.g. `planner`, `worker`, `scout`. |
| **Scenario** | A pre-built multi-agent workflow: description + roles + role prompts. |
| **Initiator** | An agent that was given a starting prompt. |
| **Responder** | An agent with no starting prompt (boots and waits on intercom). |
| **Loader** | Resolves a saved `pi-cli` config name into a `pi` argv. |
| **Backend** | A launch mechanism: `print`, `bash`, or `terminal`. |

## 4. Architecture

Package layout (`src/pi_agent_graph/`):

```
__init__.py          Public exports
models.py            Agent, Role, Scenario
loader.py            ConfigLoader (pi-cli config discovery + resolution)
fixtures.py          ScenarioFixture / RoleFixture, save/load, fixture_path
scenarios.py         Built-in scenario registry
quoting.py           POSIX / Windows / AppleScript quoting helpers
resources.py         Agent dir + extension/skill/built-in-tool resolution
launchers/
  __init__.py        launch(), LaunchOptions, LaunchResult
  validation.py      Preflight checks
  ordering.py        Responders-first ordering
  script.py          Shared launch-script renderer (print + bash)
  print.py           PrintBackend
  bash.py            BashBackend
  terminal.py        TerminalBackend (per-OS dispatch)
builder.py           AgentGraphBuilder
cli.py               Reserved entry point (help only in v1)
```

Public API (re-exported from `__init__.py`):

```python
Agent, Role, Scenario, Switch
ConfigLoader
ScenarioFixture, RoleFixture
AgentGraphBuilder
launch, LaunchOptions, LaunchResult
resolve_extension, resolve_skill, resolve_extensions, resolve_skills
```

**Layering:** `models` depends on `errors` + `resources`; `resources` depends on
`errors` only; `quoting` depends on nothing internal. `loader` and `scenarios`
depend on `models`. `fixtures` depends on `errors` only. `launchers` depend on
`models` + `quoting`. `builder` ties them together. `cli` sits on top of
`builder`.

## 5. Data model (`models.py`)

### 5.1 `Agent`

```python
@dataclass
class Agent:
    role: str
    base_argv: list[str] = field(default_factory=lambda: ["pi"])  # PI_BIN or "pi"
    name: str | None = None                              # --name; defaults to role
    session_dir: str | None = None                       # --session-dir
    system_prompt: str | None = None                     # --system-prompt
    model: str | None = None                             # --model (optionally model:thinking)
    prompt: str | None = None                            # starting positional prompt
    cwd: str | None = None
    extensions: list[str] | None = None                  # resolved -e paths
    skills: list[str] | None = None                      # resolved --skill paths
    builtin_tools: list[str] | None = None               # -bt allowlist
    exclude_tools: list[str] | None = None               # --exclude-tools names
    agent_dir: str | None = None                         # override pi's agent dir
    use_extensions: Switch = field(default_factory=Switch)
    use_skills: Switch = field(default_factory=Switch)
    use_tools: Switch = field(default_factory=Switch)
    use_context: Switch = field(default_factory=Switch)
    model_explicit: bool = False                         # model chosen in Python, not from config
```

**Managed flags.** `--name`, `--session-dir`, `--model`, and `--system-prompt`
are owned by the dataclass fields. They are **never** left inside `base_argv`.

**`set_command(argv: Sequence[str]) -> None`**
Stores a resolved `pi` command. Before storing, it extracts any managed flags
into the corresponding fields and removes them from `base_argv`. This makes
system-prompt injection a *replace*, not an append, and lets a Python-level
model override the one the saved command carried. A `--model` lifted out of a
saved command leaves `model_explicit = False`, so it is still treated as the
pi-cli default rather than a Python choice.

**Setters** (all mutate and return `None`):

- `set_name(name)`
- `set_session_dir(path)`
- `set_system_prompt(text)` — replaces the agent's system prompt
- `set_model(model, thinking=None)` — sets `--model`; appends pi's
  `model:thinking` suffix when `thinking` is given (replacing an existing known
  suffix), and strips a bare `--thinking` so the suffix is authoritative
- `set_prompt(text)`
- `set_cwd(path)` — the directory the agent starts in
- `set_dir(path)` — alias for `set_cwd`
- `set_extensions(*names, agent_dir=None)` — resolve names/paths and load
  exactly those (`-ne` + `--extension`)
- `set_skills(*names, agent_dir=None)` — resolve names/paths and load exactly
  those (`-ns` + `--skill`)
- `set_tools(*names)` — keep only these built-in tools, disabling the rest via
  `--exclude-tools` (pi-cli's `-bt` semantics; extension tools stay enabled)
- `set_exclude_tools(*names)` — exclude these tools by name via
  `--exclude-tools`, whatever registered them. Unlike `set_tools` (a keep-list),
  this also drops a built-in that an extension re-registered (for example
  `bash` under pi-parse-commands), and it survives `-nbt`. The two merge into a
  single `--exclude-tools`. Calling with no names clears the exclusions.
- `set_option(flag, value)` — replaces `flag` inside `base_argv` if present,
  else appends; used for arbitrary pass-through flags. Managed flags (including
  `--model`) route to their field instead.

**`build_argv() -> list[str]`** — pure; always returns a fresh list, never
mutates. Assembly order:

```
base_argv
+ ["--name", name]                 if name
+ ["--session-dir", session_dir]   if session_dir
+ ["--model", model]               if model
+ ["--system-prompt", system_prompt] if system_prompt
+ ["--", prompt]                   if prompt
```

The starting prompt is **always** preceded by `--` so a prompt that begins with
`-` is never parsed as a flag.

> Rationale: all mutable state lives in fields; `build_argv()` is deterministic,
> so calling `launch()` twice or re-emitting bash cannot duplicate flags.

**`display_command() -> str`** — return `build_argv()` as one readable,
pi-cli-config-style line: resolved extension/skill paths are shortened to their
config names and merged into `-e` / `-s`, excluded built-in tools are inverted
into a `-bt` allowlist when possible, and the system prompt is abbreviated to a
double-quoted tail (`--system-prompt "...last 30 characters"`).

**Model precedence.** Lowest to highest: a `--model` carried by the saved
pi-cli command (`model_explicit = False`) < a builder-wide
`AgentGraphBuilder.set_model(...)` default < a per-agent
`Agent.set_model(...)` (`model_explicit = True`). An agent with no model at any
level runs on pi's default; `AgentGraphBuilder.start()` warns about it.

**Resource precedence.** Extensions, skills, and tools follow the same order:
config < builder < per-agent. A Python choice strips that family's flags from
`base_argv` before emitting its own, so a command never carries two `-ne`/
`--extension` (or `-ns`/`--skill`, or `--exclude-tools`) sets. `set_tools` and
`set_exclude_tools` share the tool family and merge into one `--exclude-tools`.
Families not chosen in Python keep the saved config's flags.
`set_extensions("")`, `set_skills("")`, and `set_tools("")` mean "disabled" and
emit `-ne`, `-ns`, and `-nbt` respectively.

The `use_extensions`, `use_skills`, `use_tools`, and `use_context` switches have
`set(bool)` and `get()`; `.set(False)` emits `-ne`, `-ns`, `-nbt`, or `-nc`,
while `.set(True)` removes a config disable flag (a no-op when none was set).

### 5.2 `Role`

```python
@dataclass
class Role:
    name: str                      # "planner"
    description: str               # role prompt text
    config: str | None = None      # default saved pi-cli config name, e.g. "plannerv2"
```

### 5.3 `Scenario`

```python
@dataclass
class Scenario:
    key: str                       # "checklist_iteration"
    description: str               # what the workflow does
    roles: dict[str, Role]         # ordered role -> Role
```

Introspection helpers: `agent_names() -> list[str]`, `get(name) -> Role`.

## 6. Config loading (`loader.py`)

### 6.1 Config path resolution

Mirror `pi-cli`'s own logic, in this order:

1. Explicit `config_path` argument.
2. `$PI_CLI_CONFIG` (a file path).
3. `<config_dir>/config.json`, where `config_dir` is:
   `$PI_CLI_CONFIG_DIR` → `$XDG_CONFIG_HOME/pi-cli` → `~/.config/pi-cli`.
4. Honor the top-level `path` pointer in the resolved file (the `pi-cli -p`
   behavior): if present, the active file becomes `<that dir>/config.json`.

### 6.2 `ConfigLoader`

```python
class ConfigLoader:
    def __init__(self, config_path: str | None = None, pi_cli_bin: str = "pi-cli"): ...

    def list(self) -> list[str]: ...            # saved agent names (reads JSON directly)
    def get_raw(self, name: str) -> str: ...    # raw saved command string
    def get(self, name: str) -> list[str]: ...  # resolved argv
```

**`list()`** parses the config JSON directly and returns the keys of the
top-level `agents` map. No subprocess.

**`get(name)`** resolves the command by running:

```
pi-cli --dry-run -i <name>
```

with the subprocess environment setting `PI_CLI_CONFIG` to the resolved config
file (so we never mutate the user's config the way `-p/--path` would). The
stdout is parsed with `shlex.split(posix=True)`.

- `pi-cli --dry-run` prints the fully-expanded `pi ...` command with absolute
  extension/skill paths, which is why we do not reimplement name resolution.
- If `name` is not found, raise `SavedConfigNotFoundError` with the list of
  available names.
- If `pi-cli` is not on `PATH`, raise `PiCliNotFoundError`.

> Rationale: `pi-cli` is the authority on what a saved config expands to. Shelling
> out to `--dry-run` avoids duplicating its extension/skill search and quoting.

### 6.3 Errors

- `ConfigNotFoundError` — no config file at the resolved path.
- `PiCliNotFoundError` — `pi-cli` binary missing.
- `SavedConfigNotFoundError` — requested name absent.
- `ConfigParseError` — malformed JSON.

All inherit from `PiAgentGraphError`.

## 7. Scenarios (`scenarios.py`)

A registry of scenarios defined in code:

```python
SCENARIOS: dict[str, Scenario] = {
    "checklist_iteration": Scenario(...),
    "subagent_scouting": Scenario(...),
    "scout_worker_planner": Scenario(...),
}
```

The built-in scenarios (role prompts are the seed text; full text lives in code):

- **`checklist_iteration`** — planner produces a grouped checklist; worker ticks
  off one group at a time; planner validates (tests/lint/typecheck) and commits
  after each group, then hands back the next group. Roles: `planner`, `worker`.
- **`subagent_scouting`** — worker asks a fast `scout` to gather codebase context
  so the worker's own context stays clean. Roles: `worker`, `scout`.
- **`scout_worker_planner`** — planner orchestrates, worker edits, scout gathers;
  the planner's context stays small. Roles: `planner`, `worker`, `scout`.

## 8. Prompt templating

`AgentGraphBuilder` holds `shared_goal` and `shared_context`. When a scenario's
agents are materialized, each role's system prompt is rendered as:

```
You are a helpful assistant working with other agents.
You have been designated the {role} agent.

Scenario: {scenario.description}

Shared goal: {shared_goal}

Your role: {role.description}

Additional shared context: {shared_context}
```

Missing `shared_goal` / `shared_context` render as empty strings (the sections
are simply blank, not removed).

## 9. Launch pipeline (`launchers`)

### 9.1 Entry point

```python
def launch(
    agents: list[Agent],
    *,
    backend: str | None = None,   # falls back to options.backend
    options: LaunchOptions | None = None,
) -> LaunchResult: ...
```

`LaunchOptions`:

```python
@dataclass
class LaunchOptions:
    backend: str = "terminal"       # "terminal" | "bash" | "print"
    stagger: float = 1.5           # seconds between launches
    session_dir: str | None = None  # if set, each agent gets a run-scoped session dir
    run_id: str | None = None       # auto-generated when omitted
    cwd: str | None = None
    bash_path: str | None = None    # required for backend="bash"
    platform: str | None = None     # override for bash/terminal target (tests)
```

### 9.2 Preflight validation (before anything launches)

Fail with a single `ValidationError` listing **all** problems:

1. Every agent has a non-empty `base_argv`.
2. Session names are unique (name defaults to `role`).
3. No ambiguous short flags are present in `base_argv`: reject exact `-p`,
   exact `-n`, and `--print`. (`-ne`, `-ns`, `-nbt`, `-np`, `-nc` are fine.)
4. `backend` is known; for `bash`, `bash_path` is set.

Nothing is launched unless all checks pass. Never half-launch a roster.

### 9.3 Ordering

```
responders  (no prompt)  → in the order passed
initiators  (prompt)     → in the order passed
```

The initiator therefore starts last, once its peers are already up. This is the
race fix: rather than the initiator retrying until peers appear, the peer is
launched first. A `stagger` delay separates consecutive launches.

> Rationale: the agent holding the starting prompt is almost always the one that
> sends the first intercom message. Launching it last removes the start-up race
> with zero per-scenario configuration.

### 9.4 Run context

If `options.session_dir` is set, create `<session_dir>/<run_id>/` and assign
each agent `--session-dir <that path>` (unless the agent already set one). If
`run_id` is omitted, generate one from a UTC timestamp + short random suffix.

### 9.5 `LaunchResult`

```python
@dataclass
class LaunchResult:
    run_id: str
    backend: str
    commands: list[list[str]]       # argv per launched agent, in launch order
    agents: list[Agent]
    pids: list[int | None]          # None where the backend cannot report a pid
    path: str | None = None         # written script path for backend="bash"
```

`commands` is the reproducibility record; `BashBackend` can re-emit it.

## 10. Backends

### 10.1 `print`

Renders the *same launch script* the `bash` backend writes (for the current
platform) to stdout and returns a `LaunchResult` with `pids=[None, ...]`. No
processes are started. Used by tests and `AgentGraphBuilder.start_dry`.

The script is produced by a single shared renderer (`launchers/script.py`), so a
dry run is an exact preview of `save_bash`.

### 10.2 `bash`

Writes a script that reproduces the launch (opening a terminal per agent) so a
flow can be re-run by hand. The script is rendered by the same shared function
as the `print` backend (`launchers/script.py`). It:

- has a shebang (`#!/usr/bin/env bash`) and a header comment recording the
  `run_id`, timestamp, and the raw command for each agent;
- `cd`s to the recorded `cwd` if any (on Windows each `start` also passes
  `/D <agent.cwd>`, so a per-agent working directory wins over the shared one);
- invokes the same per-OS terminal dispatch as `TerminalBackend`.

Target extension/platform: `.sh` for POSIX, `.cmd` for Windows; `options.platform`
overrides the current OS (mainly for tests). Returns the written path in the
`LaunchResult` (via `BashBackend`, which also exposes the path on the result).

### 10.3 `terminal`

Opens a real terminal window per agent, detached. Dispatch by platform:

**Windows**

Both cases first write a temp `.cmd` containing
`subprocess.list2cmdline(argv)` (newlines collapsed), then open that script
with `cmd /k` so the window stays open. The raw agent command is never handed
to `wt` directly: `wt` parses its own command line and treats `;` (and
newlines) as command separators, which would split a system prompt containing
semicolons into several bogus commands — one window each.

1. If `wt` (Windows Terminal) is on `PATH`:
   `wt -w 0 nt --title <name> -d <cwd> cmd /k <tempfile>`.
2. Otherwise: `cmd /c start "" cmd /k <tempfile>`.

**macOS**

```
osascript -e 'tell application "Terminal" to do script "<quoted>"' \
          -e 'tell application "Terminal" to activate'
```

`<quoted>` is the POSIX-quoted command, then escaped for an AppleScript string
(`\` → `\\`, `"` → `\"`).

**Linux**

1. If `$TMUX` is set: `tmux new-window -n <name> -c <cwd> <argv...>`.
2. Else the first available of: `wt`, `gnome-terminal`, `konsole`,
   `xfce4-terminal`, `kitty`, `alacritty`, `xterm`, invoked with a title and
   `bash -lc '<cmd>; exec $SHELL'` so the window stays open.
3. If none is found, raise `LaunchError` naming the attempted emulators.

All backends respect `agent.cwd`.

## 11. Quoting (`quoting.py`)

- `quote_posix(value) -> str` — wrap in single quotes; `'` → `'\''`.
- `quote_windows(argv) -> str` — delegate to `subprocess.list2cmdline`.
- `quote_applescript(value) -> str` — escape `\` and `"`.

Round-tripping POSIX quotes through `shlex.split(..., posix=True)` is a required
property test.

## 12. `AgentGraphBuilder` (`builder.py`)

```python
class AgentGraphBuilder:
    def __init__(self, loader: ConfigLoader | None = None): ...

    def set_shared_goal(self, text: str) -> None: ...
    def set_shared_context(self, text: str) -> None: ...
    def set_model(self, model: str, thinking: str | None = None) -> None: ...

    def set_extensions(self, *names: str, agent_dir: str | Path | None = None) -> None: ...
    def set_skills(self, *names: str, agent_dir: str | Path | None = None) -> None: ...
    def set_tools(self, *names: str) -> None: ...
    def set_exclude_tools(self, *names: str) -> None: ...
    # Builder-level switches: use_extensions, use_skills, use_tools, use_context

    def list_scenarios(self) -> list[str]: ...
    def get_scenario(self, key: str) -> ScenarioBuilder: ...

    def save_fixture(self, identifier: str, scenario: str, *,
                     roles: dict[str, str] | None = None,
                     prompts: dict[str, str] | None = None,
                     names: dict[str, str] | None = None,
                     directory: str | Path | None = None,
                     path: str | Path | None = None) -> Path: ...
    def load_saved(self, identifier: str, *,
                   directory: str | Path | None = None,
                   path: str | Path | None = None) -> ScenarioBuilder: ...

    def get_agent_loader(self, path: str | None = None) -> ConfigLoader: ...
    def start(self, agents: list[Agent], *, backend="terminal",
              options: LaunchOptions | None = None,
              cwd: str | None = None) -> LaunchResult: ...
    def start_dry(self, agents: list[Agent], *,
                  options: LaunchOptions | None = None,
                  cwd: str | None = None) -> LaunchResult: ...
    def display_command(self, agents: list[Agent]) -> str: ...
    def save_bash(self, agents: list[Agent], path: str, *,
                  cwd: str | None = None) -> str: ...
```

`ScenarioBuilder` (returned by `get_scenario`) renders role prompts using the
builder's shared goal/context:

```python
class ScenarioBuilder:
    def get_agents(self) -> list[Agent]: ...     # agents in role order
    def get(self, role: str) -> Agent: ...       # single agent by role name
```

`get_agents()` renders the system prompt for every role, always *replacing* any
`--system-prompt` carried by the resolved config (building a dynamic prompt is
the point of the library). If a `Role.config` is set — or a fixture role
supplies one — it resolves that config into `base_argv` via
`builder.get_agent_loader()`, which uses an injected loader or lazily creates
the default one. Otherwise the caller sets it with `loader.get(...)` +
`agent.set_command(...)`, or uses the default `pi` command directly. A builder
default model or resource fills in any agent that has not chosen one (see the
precedence rules above).

`start()` is a thin wrapper: it fills default models, prints a yellow warning
for every agent that will fall back to pi's default model, then calls
`launch(agents, backend=..., options=...)`. `start_dry()` and `save_bash()`
fill default models too, but do not warn. `display_command()` fills defaults and
returns one readable command line per agent, joined by newlines (no launch
script or terminal wrapper).

```python
builder.set_model("opencode-go/mimo-v2.5", "low")   # every agent
planner.set_model("opencode-go/mimo-v2.5-pro", "high")  # one agent
# -> pi --model opencode-go/mimo-v2.5-pro:high ...
```

`save_bash()` calls `launch(..., backend="bash", options=LaunchOptions(bash_path=path))`.

### 12.1 Fixtures (`fixtures.py`)

A `ScenarioFixture` serializes a scenario's tunable pieces behind a stable
`identifier`: `scenario` (the scenario key), `shared_goal`, `shared_context`,
and a `roles` mapping of role name to a `RoleFixture` (`config` = pi-cli command
name, `prompt` = starting prompt, `name` = display name). `identifier` must be a
non-empty string with no path separators (including `.` / `..`), and `scenario`
must be non-empty. `to_dict()` / `from_dict()` round-trip the fixture;
`from_dict()` type-checks the fields and raises `FixtureFormatError` on invalid
input.

Module functions: `save_fixture(fixture, path)` and `load_fixture(path)` read and
write JSON (`FixtureNotFoundError` when the file is missing,
`FixtureFormatError` on bad JSON/schema, `FixtureError` on other I/O failures).
`fixture_path(identifier, directory=None)` returns
`<directory or "fixtures">/<identifier>.json`.

`AgentGraphBuilder.save_fixture(...)` builds a `ScenarioFixture` from the
builder's current shared goal/context plus the `roles` / `prompts` / `names`
mappings (role keys validated against the scenario) and writes it, returning the
path. `AgentGraphBuilder.load_saved(...)` loads a fixture, backfills the
builder's `shared_goal` / `shared_context`, and returns a `ScenarioBuilder`
carrying the fixture; role keys are validated eagerly. In `get_agents()`, a
fixture's per-role `config`, `name`, and `prompt` override the scenario defaults
(fixture wins); a fixture role key not present in the scenario raises
`FixtureFormatError`, and a fixture `scenario` key that is not registered raises
`ScenarioNotFoundError`.

## 13. Error taxonomy

```
PiAgentGraphError
├── ConfigNotFoundError
├── ConfigParseError
├── PiCliNotFoundError
├── SavedConfigNotFoundError
├── ScenarioNotFoundError
├── ValidationError
├── LaunchError
└── FixtureError
    ├── FixtureFormatError
    └── FixtureNotFoundError
```

### 13.1 Diagnostics (`diagnostics.py`)

User-facing diagnostics are centralized and enumerated so callers can branch on
a stable code instead of message text:

- `ErrorCode` — one code per exception class; `ERROR_CODES` maps every error
  class to its code, and `error_code(exc)` resolves the most specific one by
  walking the MRO (`UNKNOWN` for non-library exceptions).
- `WarningCode` — currently `DEFAULT_MODEL`.
- `Diagnostic` — `{code, message, agent}`, with `.format()` rendering
  `[code] message`.
- `collect_warnings(agents)` — one `DEFAULT_MODEL` diagnostic per agent with no
  model.
- `emit_warnings(warnings, stream=sys.stderr, color=True)` — prints each warning
  in yellow (`\033[33m…\033[0m`).

`AgentGraphBuilder.start()` calls `collect_warnings()` + `emit_warnings()` before
launching. New warnings get a `WarningCode` member and a collector here.

## 14. CLI (reserved)

`pyproject.toml` defines `pi-agent-graph = "pi_agent_graph:main"`. In v1 `main()`
only prints help. A real CLI (`list-scenarios`, `dry-run <scenario>`,
`start <scenario>`) is planned but **out of scope** for v1.

## 15. Testing strategy

Pure unit tests (no e2e terminal launches):

- **models** — `set_command` extracts managed flags (including `--model`);
  `set_system_prompt` replaces rather than appends; `set_model` builds the
  `model:thinking` suffix and overrides a config model; `build_argv()` is pure
  and stable across calls; `--` is always emitted before the prompt.
- **diagnostics** — error-class coverage, `error_code` MRO resolution, warning
  collection, and colored emission.
- **quoting** — POSIX round-trips through `shlex.split`; AppleScript escaping.
- **loader** — path resolution order; `list()` against a temp config;
  `get()` against a fake `pi-cli` runner; missing-name and missing-binary errors.
- **scenarios** — templating output for a known goal/context.
- **validation** — duplicate names, banned short flags, empty argv each rejected.
- **ordering** — responders precede initiators; initiators keep passed order.
- **bash** — generated script contains every agent's command and the header.

`tests/fakes.py` provides two reusable process-boundary fakes used by
integration-style tests: `FakePiCli` (a real `ConfigLoader` wired to an
in-memory `pi-cli --dry-run` runner) and `FakeLauncher` (a recording backend
registered over `print`). They run the full config -> fixture -> agents ->
launch pipeline without spawning a process.

Integration test against a real `pi-cli` is opt-in and skipped when absent. No
test opens a real terminal window.

## 16. Open questions / future work

- External scenario files (JSON/TOML) instead of code.
- Readiness probing (query `pi-cli`/intercom `list`) before launching the
  initiator, replacing or augmenting the fixed stagger.
- True graph edges (dependencies, fan-out/fan-in) with real orchestration.
- Optional output capture / post-run session export.
- A user-facing CLI.
