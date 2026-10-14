"""Launch a planner and a worker that coordinate over pi-intercom."""

from pathlib import Path

from pi_agent_graph import AgentGraphBuilder

builder = AgentGraphBuilder()

builder.set_shared_context("Use pi-intercom to message other agents. Never assume another agent can see your output.")
builder.set_shared_goal("add a feature where we can define stuff like shared context, the agent command names, the prompt, as fixtures and then load them in easily, make sure each one has an identifier or name. Then in the examples/ file I can use that to load everything. I guess I could use something like planner, worker = builder.load_saved('identifier').get_agents() that backfills the builder fields and loads the updated planner and worker agents so we can start them immediately")

planner, worker = builder.get_scenario("checklist_iteration").get_agents()

loader = builder.get_agent_loader()
planner.set_command(loader.get("planner_example"))
worker.set_command(loader.get("worker_example"))

planner.set_prompt("Start working on the plan and make the checklist, when you're ready tell the worker to get started")

# Start both agents in the repo root so they find the files they need.
repo_root = Path(__file__).resolve().parents[1]

builder.start([planner, worker], cwd=str(repo_root))
