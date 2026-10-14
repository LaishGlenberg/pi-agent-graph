"""Built-in scenarios.

A scenario pairs a human description of a workflow with the roles involved and
each role's seed prompt. The seed text is combined with the builder's shared
goal and shared context to form the agent's system prompt (see
``AgentGraphBuilder.render_system_prompt``).
"""

from __future__ import annotations

from .errors import ScenarioNotFoundError
from .models import Role, Scenario

CHECKLIST_ITERATION = Scenario(
    key="checklist_iteration",
    description=(
        "The planner generates a checklist in markdown for the worker to "
        "follow, split into multiple groups of tasks. Each group is its own "
        "mini feature made of smaller tasks that get checked off. The worker "
        "returns to the planner after completing each group; the planner "
        "validates the changes (run tests, lint, typecheck) and commits the "
        "result, then tells the worker to move on to the next group. This "
        "repeats until the task is done."
    ),
    roles={
        "planner": Role(
            name="planner",
            config=None,
            description=(
                "Generate a detailed checklist, breaking the problem into "
                "digestible groups of tasks. You validate that changes are "
                "correct (tests, lint, typecheck) before committing, then tell "
                "the worker to move on to the next group. You are the "
                "orchestrator: the worker does not test or commit."
            ),
        ),
        "worker": Role(
            name="worker",
            config=None,
            description=(
                "Implement the tasks in the checklist, ticking each box off as "
                "you finish it. Do not run the validation or commit yourself; "
                "hand the work back to the planner after each group of tasks."
            ),
        ),
    },
)

SUBAGENT_SCOUTING = Scenario(
    key="subagent_scouting",
    description=(
        "The worker asks a fast scout subagent to gather context from the "
        "codebase so the worker's own context window stays clean. The worker "
        "gives very specific instructions about exactly what information, "
        "files, and data it needs; the scout gathers it quickly and returns it."
    ),
    roles={
        "worker": Role(
            name="worker",
            config=None,
            description=(
                "Own the task. When you need context, ask the scout with very "
                "specific instructions about what files, symbols, and data you "
                "need rather than reading everything yourself. Keep your own "
                "context small."
            ),
        ),
        "scout": Role(
            name="scout",
            config=None,
            description=(
                "You are a fast retrieval subagent. Gather exactly the context "
                "the worker asked for, from the specified files and symbols, "
                "and return a concise, well-organized answer. Do not make "
                "edits or take on unrelated work."
            ),
        ),
    },
)

SCOUT_WORKER_PLANNER = Scenario(
    key="scout_worker_planner",
    description=(
        "The planner is the main orchestrator. It uses the worker to write and "
        "edit code and the scout to search and gather context, keeping the "
        "planner's own context window very small."
    ),
    roles={
        "planner": Role(
            name="planner",
            config=None,
            description=(
                "Orchestrate the work. Decide the approach, delegate edits to "
                "the worker, and delegate codebase lookups to the scout. Keep "
                "your own context window small by delegating rather than doing "
                "hands-on work yourself."
            ),
        ),
        "worker": Role(
            name="worker",
            config=None,
            description=(
                "Implement the edits the planner asks for, precisely and "
                "completely, and report back what changed."
            ),
        ),
        "scout": Role(
            name="scout",
            config=None,
            description=(
                "You are a fast retrieval subagent. Gather exactly the context "
                "you are asked for and return a concise answer. Do not edit."
            ),
        ),
    },
)

SCENARIOS: dict[str, Scenario] = {
    CHECKLIST_ITERATION.key: CHECKLIST_ITERATION,
    SUBAGENT_SCOUTING.key: SUBAGENT_SCOUTING,
    SCOUT_WORKER_PLANNER.key: SCOUT_WORKER_PLANNER,
}


def scenario_names() -> list[str]:
    """Return the registered scenario keys."""
    return list(SCENARIOS)


def get_scenario(key: str) -> Scenario:
    """Return a scenario by key, or raise :class:`ScenarioNotFoundError`."""
    try:
        return SCENARIOS[key]
    except KeyError as error:
        available = ", ".join(SCENARIOS)
        raise ScenarioNotFoundError(
            f"unknown scenario {key!r} (available: {available})"
        ) from error
