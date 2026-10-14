"""The high-level builder API."""

from __future__ import annotations

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
    ) -> LaunchResult:
        return launch(agents, backend=backend, options=options)

    def start_dry(
        self, agents: list[Agent], *, options: LaunchOptions | None = None
    ) -> LaunchResult:
        """Print the commands :meth:`start` would run, without launching."""
        return launch(agents, backend="print", options=options)

    def save_bash(self, agents: list[Agent], path: str) -> str:
        result = launch(
            agents,
            backend="bash",
            options=LaunchOptions(bash_path=path),
        )
        assert result.path is not None
        return result.path
