"""The high-level builder API."""

from __future__ import annotations

from dataclasses import replace

from .launchers import LaunchOptions, LaunchResult, launch
from .loader import ConfigLoader
from .models import Agent, Role, Scenario
from .scenarios import SCENARIOS, get_scenario as _lookup_scenario

SYSTEM_PROMPT_TEMPLATE = """\
You are a helpful assistant working with other agents.
You have been designated the {role} agent.

Scenario: {scenario}

Shared goal: {goal}

Your role: {description}

Additional shared context: {context}"""


def render_system_prompt(
    role: Role, scenario_description: str, goal: str, context: str
) -> str:
    """Render a role's system prompt from the shared goal and context."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        role=role.name,
        scenario=scenario_description,
        goal=goal,
        description=role.description,
        context=context,
    )


def _with_cwd(
    options: LaunchOptions | None, cwd: str | None
) -> LaunchOptions | None:
    """Return *options* with ``cwd`` applied, or ``None`` unchanged.

    ``cwd`` overrides any ``options.cwd``; a fresh ``LaunchOptions`` is built
    only when needed, so a caller's options object is never mutated.
    """
    if cwd is None:
        return options
    if options is None:
        return LaunchOptions(cwd=cwd)
    return replace(options, cwd=cwd)


class ScenarioBuilder:
    """Materializes a :class:`Scenario` into :class:`Agent` objects."""

    def __init__(self, builder: "AgentGraphBuilder", scenario: Scenario) -> None:
        self.builder = builder
        self.scenario = scenario

    def get_agents(self) -> list[Agent]:
        agents: list[Agent] = []
        builder = self.builder
        for name, role in self.scenario.roles.items():
            system_prompt = render_system_prompt(
                role,
                self.scenario.description,
                builder.shared_goal,
                builder.shared_context,
            )
            agent = Agent(role=name, system_prompt=system_prompt)
            loader = builder._loader
            if role.config and loader is not None:
                agent.set_command(loader.get(role.config))
            agents.append(agent)
        return agents

    def get(self, role: str) -> Agent:
        for agent in self.get_agents():
            if agent.role == role:
                return agent
        raise KeyError(role)


class AgentGraphBuilder:
    """Builds agents from scenarios and launches them."""

    def __init__(self, loader: ConfigLoader | None = None) -> None:
        self._loader = loader
        self.shared_goal = ""
        self.shared_context = ""

    # -- shared prompt context -------------------------------------------
    def set_shared_goal(self, text: str) -> None:
        self.shared_goal = text

    def set_shared_context(self, text: str) -> None:
        self.shared_context = text

    def render_system_prompt(
        self, role: Role, scenario_description: str = ""
    ) -> str:
        return render_system_prompt(
            role,
            scenario_description,
            self.shared_goal,
            self.shared_context,
        )

    # -- scenarios --------------------------------------------------------
    def list_scenarios(self) -> list[str]:
        return list(SCENARIOS)

    def get_scenario(self, key: str) -> ScenarioBuilder:
        return ScenarioBuilder(self, _lookup_scenario(key))

    # -- loader -----------------------------------------------------------
    def get_agent_loader(self, path: str | None = None) -> ConfigLoader:
        if path is not None:
            return ConfigLoader(path)
        if self._loader is None:
            self._loader = ConfigLoader()
        return self._loader

    # -- launching --------------------------------------------------------
    def start(
        self,
        agents: list[Agent],
        *,
        backend: str | None = None,
        options: LaunchOptions | None = None,
        cwd: str | None = None,
    ) -> LaunchResult:
        """Launch *agents*, optionally starting each one in *cwd*.

        ``cwd`` applies to every agent that does not already have its own
        working directory set (see :meth:`Agent.set_cwd`), so per-agent values
        win.
        """
        return launch(
            agents,
            backend=backend,
            options=_with_cwd(options, cwd),
        )

    def start_dry(
        self,
        agents: list[Agent],
        *,
        options: LaunchOptions | None = None,
        cwd: str | None = None,
    ) -> LaunchResult:
        """Print the commands :meth:`start` would run, without launching."""
        return launch(
            agents,
            backend="print",
            options=_with_cwd(options, cwd),
        )

    def save_bash(
        self, agents: list[Agent], path: str, *, cwd: str | None = None
    ) -> str:
        result = launch(
            agents,
            backend="bash",
            options=_with_cwd(LaunchOptions(bash_path=path), cwd),
        )
        assert result.path is not None
        return result.path
