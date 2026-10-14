"""Launch a planner and a worker that coordinate over pi-intercom."""

from pi_agent_graph import AgentGraphBuilder

builder = AgentGraphBuilder()

builder.set_shared_context("Use pi-intercom to message other agents. Never assume another agent can see your output.")
builder.set_shared_goal("Design a new feature for my website: a modern, sleek, professional-looking React component with a white background.")

planner, worker = builder.get_scenario("checklist_iteration").get_agents()

loader = builder.get_agent_loader()
planner.set_command(loader.get("planner_example"))
worker.set_command(loader.get("worker_example"))

planner.set_prompt("Start working on the plan: decide which libraries and React components to use and what the styles should be, create a checklist, then hand the first group of tasks to the worker.")

builder.start_dry([planner, worker])
