"""The high-level builder API."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from . import fixtures
from .errors import FixtureFormatError
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

    def __init__(
        self,
        builder: "AgentGraphBuilder",
        scenario: Scenario,
        fixture: fixtures.ScenarioFixture | None = None,
    ) -> None:
        self.builder = builder
        self.scenario = scenario
        self.fixture = fixture

    def _validate_fixture(self) -> None:
        """Raise :class:`FixtureFormatError` on unknown fixture role keys."""
        if self.fixture is None:
            return
        for key in self.fixture.roles:
            if key not in self.scenario.roles:
                raise FixtureFormatError(
                    f"fixture {self.fixture.identifier!r} has role {key!r} "
                    f"not in scenario {self.scenario.key!r}"
                )

    def get_agents(self) -> list[Agent]:
        self._validate_fixture()
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
            # Fixture wins over scenario defaults when present for this role.
            if self.fixture is not None:
                fixture_role = self.fixture.roles.get(name)
                if fixture_role is not None:
                    if fixture_role.config:
                        fixture_loader = builder.get_agent_loader()
                        agent.set_command(fixture_loader.get(fixture_role.config))
                    if fixture_role.name:
                        agent.set_name(fixture_role.name)
                    if fixture_role.prompt:
                        agent.set_prompt(fixture_role.prompt)
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

    # -- fixtures ---------------------------------------------------------
    def save_fixture(
        self,
        identifier: str,
        scenario: str,
        *,
        roles: dict[str, str] | None = None,
        prompts: dict[str, str] | None = None,
        names: dict[str, str] | None = None,
        directory: str | Path | None = None,
        path: str | Path | None = None,
    ) -> Path:
        """Write a fixture for *scenario* and return the written path.

        ``roles`` maps a role name to a pi-cli command name; ``prompts`` and
        ``names`` optionally map a role name to a starting prompt / display
        name. ``shared_goal`` / ``shared_context`` default to the builder's
        current values.
        """
        scenario_obj = _lookup_scenario(scenario)
        role_keys = set(roles or {}) | set(prompts or {}) | set(names or {})
        for key in role_keys:
            if key not in scenario_obj.roles:
                raise FixtureFormatError(
                    f"role {key!r} not in scenario {scenario!r}"
                )
        role_fixtures: dict[str, fixtures.RoleFixture] = {}
        for key in role_keys:
            role_fixtures[key] = fixtures.RoleFixture(
                config=(roles or {}).get(key),
                prompt=(prompts or {}).get(key),
                name=(names or {}).get(key),
            )
        fixture = fixtures.ScenarioFixture(
            identifier=identifier,
            scenario=scenario,
            shared_goal=self.shared_goal,
            shared_context=self.shared_context,
            roles=role_fixtures,
        )
        target = path if path is not None else fixtures.fixture_path(identifier, directory)
        return fixtures.save_fixture(fixture, target)

    def load_saved(
        self,
        identifier: str,
        *,
        directory: str | Path | None = None,
        path: str | Path | None = None,
    ) -> ScenarioBuilder:
        """Load a saved fixture, backfilling shared goal/context.

        Returns a :class:`ScenarioBuilder` bound to the fixture's scenario and
        carrying the fixture so its per-role overrides apply in
        :meth:`ScenarioBuilder.get_agents`.
        """
        target = path if path is not None else fixtures.fixture_path(identifier, directory)
        fixture = fixtures.load_fixture(target)
        self.shared_goal = fixture.shared_goal
        self.shared_context = fixture.shared_context
        return ScenarioBuilder(self, _lookup_scenario(fixture.scenario), fixture=fixture)

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
