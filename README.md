# pi-agent-graph

A small Python library for building and launching **multi-agent pi workflows**.

Describe a roster of agents — a role, a resolved `pi` command, a session name,
and an optional starting prompt — and `pi-agent-graph` launches each one in its
own terminal window, where they coordinate over `pi-intercom`.

> **Full design details live in [SPEC.md](./SPEC.md).** This README is the
> overview; the spec is the source of truth.

## Why

A two- or three-agent pi setup means hand-writing several long
`pi-cli ...` commands, remembering each agent's role prompt, and getting the
start-up order right so the agents can actually reach each other. That is
tedious to set up and easy to get subtly wrong (wrong flags, stale paths,
a planner that messages a worker that isn't up yet).

`pi-agent-graph` turns that into a declarative roster:

- **Commands come from your config.** Saved agents in
  `pi-cli`'s `config.json` are resolved by name, so extensions, skills, models,
  and prompts stay in one place.
- **Scenarios carry the role prompts.** Pick a workflow, get agents with the
  right responsibilities already described.
- **Launch order is handled.** Agents without a prompt start first; the agent
  holding the starting prompt starts last, so it never races its peers.
- **It is reproducible.** Every launch can also be emitted as a shell script.

## How it works

1. **Build** — an `AgentGraphBuilder` + a scenario produces `Agent` objects,
   each with a role, a rendered system prompt, a session name, and (later) a
   resolved `pi` command.
2. **Resolve** — a `ConfigLoader` reads `pi-cli`'s saved agents and expands a
   name into a full `pi` command via `pi-cli --dry-run`, so paths are absolute.
3. **Launch** — a backend starts each agent. `terminal` opens real windows,
   `bash` writes a script, `print` is a dry-run/test mode.

## Install

This project is managed with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

`pi-cli` must be installed and on `PATH` for saved-agent resolution, and at
least one terminal emulator must be available for the `terminal` backend (see
[Platform support](#platform-support)).

## Development

```bash
uv sync                 # install runtime + dev dependencies
uv run pytest           # run the test suite
uv run pi-agent-graph   # console entry point (prints help in v1)
```

## Manual end-to-end run

`examples/checklist_iteration.py` is a complete usage example: it loads two
saved `pi-cli` configs, builds the `checklist_iteration` agents, and opens a
terminal window for each (worker first, planner last).

```bash
uv run python examples/checklist_iteration.py
```

It uses the saved configs `plannerv2` and `workerv3`; change those two lines to
match your own.

## Quickstart

```python
from pi_agent_graph import AgentGraphBuilder

builder = AgentGraphBuilder()
builder.set_shared_context(
    "Use pi-intercom to message other agents. "
    "Never assume another agent can see your output."
)
builder.set_shared_goal(
    "Design a modern, sleek React feature: pick libraries and components."
)

# Pick a scenario -> agents with role prompts already rendered.
planner, worker = builder.get_scenario("checklist_iteration").get_agents()

# Bind each agent to a saved pi-cli config.
loader = builder.get_agent_loader()  # ~/.config/pi-cli/config.json
planner.set_command(loader.get("plannerv2"))
worker.set_command(loader.get("workerv3"))

planner.set_prompt(
    "Draft the plan, choose libraries and components, "
    "then create the checklist and hand off to the worker."
)

# Optional: pick a model. A builder-wide default applies to every agent;
# a per-agent call overrides it. Neither is required (pi's default is used).
builder.set_model("opencode-go/mimo-v2.5", "low")
planner.set_model("opencode-go/mimo-v2.5-pro", "high")

# Start every agent in a workspace. Per-agent overrides win, so
# `planner.set_dir("C:/work/api")` (or `set_cwd`) takes precedence.
workspace = "C:/Users/lg/projects/my-app"

# Preview exactly what will run, without opening anything.
builder.start_dry([planner, worker], cwd=workspace)

# Or return pi-cli-config-style lines (resource names, abbreviated system prompt).
lines = builder.display_command([planner, worker])

# The worker (no prompt) launches first; the planner launches last.
result = builder.start([planner, worker], cwd=workspace)
print(result.commands)  # exact argv per agent, in launch order

# The same flow as a reproducible script.
builder.save_bash([planner, worker], path="flows/checklist.sh", cwd=workspace)
```

The lower-level API is importable on its own for custom flows:

```python
from pi_agent_graph import launch

result = launch([planner, worker], backend="print")
```

## Building commands in Python

You do not need a saved pi-cli config. Agents default to `PI_BIN` (or `pi`),
and extension/skill/tool names are resolved with the same search rules pi-cli
uses:

```python
agent = builder.get_scenario("checklist_iteration").get_agents()[0]
agent.set_extensions("pi-intercom, rpiv-todo, rtk")
agent.set_skills("pi-intercom")
agent.set_tools("read", "bash")          # pi-cli's -bt semantics
agent.use_context.set(False)             # -> -nc
```

Python choices replace the matching flags from a saved config; families you do
not touch keep the config's values. `set_extensions("")` (or
`use_extensions.set(False)`) disables extensions, and the same pattern applies
to skills, tools, and context files.

## Model selection

Set a model per agent, or a default for the whole roster. `thinking` is
appended as pi's `model:thinking` suffix:

```python
builder.set_model("opencode-go/mimo-v2.5", "low")        # every agent
planner.set_model("opencode-go/mimo-v2.5-pro", "high")   # planner only
# -> pi --model opencode-go/mimo-v2.5-pro:high ...
```

Precedence, lowest to highest:

1. a `--model` carried by the saved pi-cli command;
2. the builder-wide `set_model(...)` default;
3. a per-agent `set_model(...)`.

When no model is set at any level, pi uses its own default and `start()` prints
a yellow warning naming the agents that will fall back. Our rendered system
prompt always replaces a `--system-prompt` saved in the pi-cli config, because
building that prompt dynamically is the point of the library.

## Built-in scenarios

Scenarios are defined in code (`scenarios.py`) and are meant to be extended.

| Scenario | Roles | What it does |
| --- | --- | --- |
| `checklist_iteration` | `planner`, `worker` | Planner writes a grouped checklist; the worker ticks off one group at a time; the planner validates (tests / lint / typecheck) and commits after each group, then hands over the next. |
| `subagent_scouting` | `worker`, `scout` | The worker asks a fast `scout` to gather codebase context, keeping the worker's own context window clean. |
| `scout_worker_planner` | `planner`, `worker`, `scout` | The planner orchestrates, the worker edits, the scout gathers — so the planner's context stays small. |

Each role has a seed description that is combined with your shared goal and
shared context into the agent's system prompt.

## Fixtures

A fixture captures a scenario's tunable pieces — the shared context, the shared
goal, and each role's pi-cli command name and starting prompt — behind a stable
`identifier`, so it can be saved to disk and reloaded without re-entering the
fields by hand.

```python
from pi_agent_graph import AgentGraphBuilder

builder = AgentGraphBuilder()

# Load a saved fixture by identifier; this backfills the builder's shared
# goal/context and returns a ScenarioBuilder carrying the fixture.
scenario = builder.load_saved(
    "checklist_iteration_demo", directory="examples/fixtures"
)
planner, worker = scenario.get_agents()  # fixture configs resolved via pi-cli

builder.start([planner, worker], cwd=".")
```

`ScenarioFixture` holds the `identifier`, the `scenario` key, `shared_goal`,
`shared_context`, and a `roles` mapping of role name to a `RoleFixture` (`config`
= pi-cli command name, `prompt` = starting prompt, `name` = display name). Save
the current builder state as a fixture with `builder.save_fixture(...)`:

```python
builder.set_shared_goal("Design a React feature.")
path = builder.save_fixture(
    "my_demo",
    "checklist_iteration",
    roles={"planner": "plannerv2", "worker": "workerv3"},
    prompts={"planner": "Draft the plan."},
    directory="fixtures",  # default directory is "fixtures"
)
```

`fixture_path(identifier, directory=None)` returns
`<directory or "fixtures">/<identifier>.json`. A saved fixture is plain JSON that
matches `ScenarioFixture.to_dict()`:

```json
{
  "identifier": "checklist_iteration_demo",
  "scenario": "checklist_iteration",
  "shared_goal": "Design a React feature.",
  "shared_context": "Use pi-intercom to message other agents.",
  "roles": {
    "planner": {"config": "plannerv2", "prompt": "Draft the plan.", "name": null},
    "worker": {"config": "workerv3", "prompt": null, "name": null}
  }
}
```

Fixture problems raise `FixtureFormatError` (bad fields, unknown role) or
`FixtureNotFoundError` (missing file), both under `FixtureError`. A fixture
`identifier` must be a non-empty string with no path separators (`.`, `..`
included). A fixture role's `config` is resolved through
`builder.get_agent_loader()` (injected or lazily created), so
`load_saved(...).get_agents()` returns ready-to-start agents without extra
setup.

## Platform support

`pi-agent-graph` targets Windows, macOS, and Linux.

| Platform | `terminal` backend |
| --- | --- |
| Windows | A temp `.cmd` is opened with `cmd /k`, via Windows Terminal (`wt`) when present, else `cmd /c start`. This keeps `wt` from splitting system prompts on `;`. |
| macOS | Terminal.app via `osascript`. |
| Linux | `tmux` when inside a session, else `wt` → `gnome-terminal` → `konsole` → `xfce4-terminal` → `kitty` → `alacritty` → `xterm`. |

`bash` emits a `.sh` script on POSIX and a `.cmd` script on Windows.

## Status

v1 is implemented: agent/scenario building, `pi-cli` config resolution, and the
`print`, `bash`, and `terminal` launch backends, with a comprehensive test
suite. The design lives in [SPEC.md](./SPEC.md).

Not yet implemented: a user-facing CLI (the entry point prints help), output
capture, auto-readiness probing beyond launch ordering, and true graph
(edge/DAG) orchestration.
