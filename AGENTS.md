# AGENTS.md — pi-agent-graph

Guidance for agents working in this repository.

This is a uv repo, use `uv add` for dependencies.

## Commands

```bash
uv sync                       # install runtime + dev dependencies
uv run pytest                 # full test suite
uv run pytest tests/test_models.py -q
uv run pytest -k ordering     # subset by name
uv run ruff check .           # lint
uv run ruff format --check .  # formatting check
uv run mypy                   # static type check (strict, src/)
uv run pi-agent-graph         # console entry point (prints help in v1)
```

Ruff (lint + format) and mypy (strict, `src/`) are configured; CI runs both plus
the test suite. `*.md` is excluded from Ruff so code blocks in the docs are not
reformatted.

## Layout

```
src/pi_agent_graph/
  errors.py        Exception hierarchy (all inherit PiAgentGraphError)
  models.py        Agent, Role, Scenario; managed-flag extraction
  quoting.py       POSIX / Windows / AppleScript quoting
  loader.py        ConfigLoader: pi-cli config discovery + --dry-run resolution
  fixtures.py      ScenarioFixture / RoleFixture; JSON save/load
  scenarios.py     Built-in scenario registry (code, not files)
  builder.py       AgentGraphBuilder + ScenarioBuilder
  cli.py           Reserved console entry point (help only)
  launchers/
    __init__.py    launch(), LaunchOptions, LaunchResult, backend registry
    types.py       LaunchOptions + LaunchResult dataclasses
    validation.py  Preflight checks (runs before anything launches)
    ordering.py    Responders-first ordering
    script.py      Shared launch-script renderer (print + bash)
    print.py       PrintBackend   (dry-run / tests)
    bash.py        BashBackend    (writes .sh / .cmd)
    terminal.py    TerminalBackend + pure per-OS invocation builders
tests/             One test module per source module; ~40 tests per area
examples/          Manual runnable examples (not part of the test suite)
```

`README.md` is the overview; `SPEC.md` is the design source of truth. Keep both
in sync with behavior changes.

## Invariants

- **Managed flags live in fields.** `--name`, `--session-dir`, and
  `--system-prompt` are extracted out of `base_argv` into `Agent` fields.
  Setting a system prompt must **replace**, never append — a command must never
  contain two `--system-prompt` flags. `build_argv()` is pure; never mutate
  `base_argv` while rendering.
- **Long flags only.** Preflight rejects the exact tokens `-p`, `-n`, and
  `--print` because they are ambiguous between `pi` and `pi-cli` (or make a
  session non-interactive). `-ne`/`-ns`/`-nbt`/`-np`/`-nc` are fine.
- **Responders launch before prompt-bearers.** The agent holding the starting
  prompt starts last so it never races its peers. Order is otherwise the input
  order; do not re-sort beyond this rule.
- **Never mutate the user's pi-cli config.** Resolve commands with
  `pi-cli --dry-run -i <name>` and pin `PI_CLI_CONFIG` to the resolved file.
  Do not use `pi-cli -p/--path` (it writes a `path` pointer).
- **No real process launches in tests.** Validate backends via their pure
  invocation builders (`windows_wt_command`, `linux_emulator_command`, ...) or
  an injected fake `popen`/`runner`.
- **Always `--` before a starting prompt** so a prompt beginning with `-` is
  never parsed as a flag.
- **Do not add new e2e tests without the user's permission.** Manual e2e runs
  live under `examples/` and are run by hand.

## Testing

- Put one test module per source module under `tests/`.
- Prefer pure-function tests and dependency injection (`runner`, `which`,
  `popen`) over mocking internals.
- `tests/test_loader.py` injects a fake subprocess runner — never shell out to
  a real `pi-cli` in tests.
- Parametrize edge cases (quoting, banned flags, emulators) rather than writing
  near-duplicates.

## Git

This repo uses `master` and had no commits when the project was scaffolded.
Commit implementation and tests together; keep generated launch scripts
(`flows/`, `.sh`, `.cmd`) out of version control unless intentionally added.
