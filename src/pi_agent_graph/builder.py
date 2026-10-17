"""The high-level builder API."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from . import diagnostics, fixtures
from .errors import FixtureFormatError
from .launchers import LaunchOptions, LaunchResult, launch
from .loader import ConfigLoader
from .models import Agent, Role, Scenario, Switch
from .resources import (
    resolve_builtin_tools,
    resolve_extensions,
    resolve_skills,
)
from .scenarios import SCENARIOS
from .scenarios import get_scenario as _lookup_scenario

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


def _with_cwd(options: LaunchOptions | None, cwd: str | None) -> LaunchOptions | None:
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
        builder: AgentGraphBuilder,
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

    def _fixture_role(self, name: str) -> fixtures.RoleFixture | None:
        if self.fixture is None:
            return None
        return self.fixture.roles.get(name)

    def _resolve_config(self, name: str, role: Role) -> str | None:
        """The config to resolve for *name*; a fixture role wins over the scenario."""
        fixture_role = self._fixture_role(name)
        if fixture_role is not None and fixture_role.config:
            return fixture_role.config
        return role.config

    def get_agents(self) -> list[Agent]:
        self._validate_fixture()
        agents: list[Agent] = []
        builder = self.builder
        for name, role in self.scenario.roles.items():
            agent = Agent(role=name)
            # Configs always resolve through the builder's loader (lazily
            # created when none was injected), so scenario and fixture roles
            # resolve identically instead of only fixtures auto-loading.
            config = self._resolve_config(name, role)
            if config:
                agent.set_command(builder.get_agent_loader().get(config))
            # Our rendered system prompt always wins: it replaces any prompt
            # the saved command carried, because building a dynamic prompt is
            # the whole point of this library.
            agent.set_system_prompt(
                render_system_prompt(
                    role,
                    self.scenario.description,
                    builder.shared_goal,
                    builder.shared_context,
                )
            )
            # Fixture name/prompt win over anything the config set.
            fixture_role = self._fixture_role(name)
            if fixture_role is not None:
                if fixture_role.name:
                    agent.set_name(fixture_role.name)
                if fixture_role.prompt:
                    agent.set_prompt(fixture_role.prompt)
            # A builder-level default fills only agents that did not choose a
            # model or resource in Python; config values are overridden by it.
            builder._fill_defaults(agent)
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
        self.default_model: str | None = None
        self.default_thinking: str | None = None
        self.default_extensions: list[str] | None = None
        self.default_skills: list[str] | None = None
        self.default_builtin_tools: list[str] | None = None
        self.agent_dir: str | None = None
        self.use_extensions = Switch()
        self.use_skills = Switch()
        self.use_tools = Switch()
        self.use_context = Switch()

    # -- shared prompt context -------------------------------------------
    def set_shared_goal(self, text: str) -> None:
        self.shared_goal = text

    def set_shared_context(self, text: str) -> None:
        self.shared_context = text

    def set_model(self, model: str, thinking: str | None = None) -> None:
        """Set a default model for every agent that has not chosen one.

        Precedence: a per-agent :meth:`Agent.set_model` wins over this default,
        which in turn overrides a model carried by the saved pi-cli command.
        ``thinking`` is appended as pi's ``model:thinking`` suffix.
        """
        self.default_model = model
        self.default_thinking = thinking

    def _fill_default_model(self, agent: Agent) -> None:
        if self.default_model is not None and not agent.model_explicit:
            agent.set_model(self.default_model, self.default_thinking)

    # -- resource defaults ------------------------------------------------
    def set_extensions(self, *names: str, agent_dir: str | Path | None = None) -> None:
        """Load these extensions for every agent that did not choose its own.

        A per-agent :meth:`Agent.set_extensions` always wins, and either choice
        replaces extensions carried by a saved pi-cli command. No names means
        disable extensions (``-ne``).
        """
        resolved = resolve_extensions(names, agent_dir or self.agent_dir)
        if not resolved:
            self.default_extensions = []
            self.use_extensions.set(False)
            return
        self.default_extensions = resolved
        self.use_extensions.set(True)

    def set_skills(self, *names: str, agent_dir: str | Path | None = None) -> None:
        """Load these skills for every agent that did not choose its own.

        A per-agent :meth:`Agent.set_skills` always wins, and no names means
        disable skills (``-ns``).
        """
        resolved = resolve_skills(names, agent_dir or self.agent_dir)
        if not resolved:
            self.default_skills = []
            self.use_skills.set(False)
            return
        self.default_skills = resolved
        self.use_skills.set(True)

    def set_tools(self, *names: str) -> None:
        """Keep only these built-in tools for every agent that did not choose.

        No names means disable built-in tools (``-nbt``), leaving extension
        tools enabled.
        """
        tools = resolve_builtin_tools(names)
        if not tools:
            self.default_builtin_tools = []
            self.use_tools.set(False)
            return
        self.default_builtin_tools = tools
        self.use_tools.set(True)

    def _fill_default_resources(self, agent: Agent) -> None:
        if agent.agent_dir is None and self.agent_dir is not None:
            agent.agent_dir = self.agent_dir

        if not agent.use_extensions.explicit and self.use_extensions.explicit:
            agent.use_extensions.set(self.use_extensions.get())
        if agent.extensions is None and self.default_extensions is not None:
            agent.extensions = list(self.default_extensions)

        if not agent.use_skills.explicit and self.use_skills.explicit:
            agent.use_skills.set(self.use_skills.get())
        if agent.skills is None and self.default_skills is not None:
            agent.skills = list(self.default_skills)

        if not agent.use_tools.explicit and self.use_tools.explicit:
            agent.use_tools.set(self.use_tools.get())
        if agent.builtin_tools is None and self.default_builtin_tools is not None:
            agent.builtin_tools = list(self.default_builtin_tools)

        if not agent.use_context.explicit and self.use_context.explicit:
            agent.use_context.set(self.use_context.get())

    def _fill_defaults(self, agent: Agent) -> None:
        self._fill_default_model(agent)
        self._fill_default_resources(agent)

    def _fill_all_defaults(self, agents: Iterable[Agent]) -> None:
        for agent in agents:
            self._fill_defaults(agent)

    def render_system_prompt(self, role: Role, scenario_description: str = "") -> str:
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
        name. The fixture's shared goal/context are taken from the builder's
        current values.
        """
        scenario_obj = _lookup_scenario(scenario)
        role_keys = set(roles or {}) | set(prompts or {}) | set(names or {})
        for key in role_keys:
            if key not in scenario_obj.roles:
                raise FixtureFormatError(f"role {key!r} not in scenario {scenario!r}")
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
        target = (
            path if path is not None else fixtures.fixture_path(identifier, directory)
        )
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
        target = (
            path if path is not None else fixtures.fixture_path(identifier, directory)
        )
        fixture = fixtures.load_fixture(target)
        self.shared_goal = fixture.shared_goal
        self.shared_context = fixture.shared_context
        scenario_builder = ScenarioBuilder(
            self, _lookup_scenario(fixture.scenario), fixture=fixture
        )
        # Validate role keys eagerly so a bad fixture fails at load time, not
        # later when agents are materialized.
        scenario_builder._validate_fixture()
        return scenario_builder

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
        win. Agents with no model fall back to pi's default and are warned
        about before launch.
        """
        self._fill_all_defaults(agents)
        diagnostics.emit_warnings(diagnostics.collect_warnings(agents))
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
        self._fill_all_defaults(agents)
        return launch(
            agents,
            backend="print",
            options=_with_cwd(options, cwd),
        )

    def save_bash(
        self, agents: list[Agent], path: str, *, cwd: str | None = None
    ) -> str:
        self._fill_all_defaults(agents)
        result = launch(
            agents,
            backend="bash",
            options=_with_cwd(LaunchOptions(bash_path=path), cwd),
        )
        assert result.path is not None
        return result.path
