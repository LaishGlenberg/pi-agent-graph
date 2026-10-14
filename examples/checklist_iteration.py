#!/usr/bin/env python
"""Manual end-to-end example: launch a planner + worker over pi-intercom.

By default this only *previews* the exact `pi` commands. Nothing is opened until
you pass ``--launch``.

    uv run python examples/checklist_iteration.py
    uv run python examples/checklist_iteration.py --launch
    uv run python examples/checklist_iteration.py --save flows/checklist.cmd

The worker is started first and the planner last, so the planner (the agent with
the starting prompt) never sends an intercom message before the worker is up.
"""

from __future__ import annotations

import argparse
import sys

from pi_agent_graph import (
    AgentGraphBuilder,
    ConfigLoader,
    LaunchError,
    PiAgentGraphError,
    ValidationError,
)

DEFAULT_GOAL = (
    "Design a new feature for my website: a modern, sleek, professional-looking "
    "React component with a white background."
)
DEFAULT_CONTEXT = (
    "Use pi-intercom to message the other agent. Never assume the other agent "
    "can see your output."
)
DEFAULT_PROMPT = (
    "Start working on the plan: decide which libraries and React components to "
    "use and what the styles should be, then create a checklist and hand the "
    "first group of tasks to the worker."
)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--planner-config", default="planner")
    parser.add_argument("--worker-config", default="worker")
    parser.add_argument("--goal", default=DEFAULT_GOAL)
    parser.add_argument("--context", default=DEFAULT_CONTEXT)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument(
        "--launch", action="store_true", help="open real terminal windows"
    )
    parser.add_argument(
        "--save", metavar="PATH", help="write a launch script and exit"
    )
    return parser.parse_args(argv)


def resolve_config(
    available: list[str], requested: str, fallback: str | None
) -> str:
    """Pick a saved config, falling back with a warning when allowed."""
    if requested in available:
        return requested
    if fallback is not None and fallback in available:
        print(
            f"warning: saved config {requested!r} not found; "
            f"using {fallback!r} instead",
            file=sys.stderr,
        )
        return fallback
    listing = ", ".join(available) or "<none>"
    raise SystemExit(
        f"error: saved config {requested!r} not found. available: {listing}"
    )


def build(argv: list[str] | None):
    args = parse_args(argv)
    loader = ConfigLoader()
    available = loader.list()

    # A dedicated planner config is optional; fall back to the worker's.
    planner_config = resolve_config(available, args.planner_config, args.worker_config)
    worker_config = resolve_config(available, args.worker_config, None)

    builder = AgentGraphBuilder()
    builder.set_shared_goal(args.goal)
    builder.set_shared_context(args.context)

    planner, worker = builder.get_scenario("checklist_iteration").get_agents()
    planner.set_command(loader.get(planner_config))
    worker.set_command(loader.get(worker_config))
    planner.set_prompt(args.prompt)

    return args, builder, [planner, worker]


def main(argv: list[str] | None = None) -> int:
    try:
        args, builder, agents = build(argv)
    except PiAgentGraphError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.save:
        path = builder.save_bash(agents, args.save)
        print(f"wrote {path}")
        return 0

    # Always preview first so the exact commands are visible.
    builder.start(agents, backend="print")

    if not args.launch:
        print(
            "\n(dry run) pass --launch to open real terminal windows.",
            file=sys.stderr,
        )
        return 0

    try:
        result = builder.start(agents, backend="terminal")
    except (ValidationError, LaunchError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    roles = ", ".join(agent.role for agent in result.agents)
    print(f"launched run {result.run_id}: {roles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
