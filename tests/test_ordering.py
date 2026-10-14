"""Tests for launch ordering."""

from __future__ import annotations

from pi_agent_graph.launchers.ordering import order_agents
from pi_agent_graph.models import Agent


def make(role: str, prompt: str | None = None) -> Agent:
    agent = Agent(role=role, prompt=prompt)
    agent.set_command(["pi"])
    return agent


def test_responders_launch_before_initiators():
    planner = make("planner", "go")
    worker = make("worker")
    assert [a.role for a in order_agents([planner, worker])] == ["worker", "planner"]


def test_groups_preserve_input_order():
    initiator_a = make("a", "go")
    responder_c = make("c")
    initiator_b = make("b", "go")
    responder_d = make("d")
    ordered = order_agents([initiator_a, responder_c, initiator_b, responder_d])
    assert [a.role for a in ordered] == ["c", "d", "a", "b"]


def test_no_prompts_preserves_order():
    agents = [make("a"), make("b"), make("c")]
    assert [a.role for a in order_agents(agents)] == ["a", "b", "c"]


def test_all_prompts_preserves_order():
    agents = [make("a", "x"), make("b", "y")]
    assert [a.role for a in order_agents(agents)] == ["a", "b"]


def test_empty():
    assert order_agents([]) == []


def test_returns_same_objects():
    agents = [make("a", "x"), make("b")]
    ordered = order_agents(agents)
    assert {id(a) for a in ordered} == {id(a) for a in agents}
