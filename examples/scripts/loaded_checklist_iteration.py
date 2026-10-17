"""Launch a planner and a worker configured from a saved fixture."""

from pathlib import Path

from pi_agent_graph import AgentGraphBuilder

builder = AgentGraphBuilder()

# The fixture carries the shared goal/context and each role's pi-cli command
# name + starting prompt, all under a stable identifier.
scenario = builder.load_saved(
    "checklist_iteration_demo",
    directory=str(Path(__file__).resolve().parent / "fixtures"),
)
planner, worker = scenario.get_agents()

# Start both agents in the repo root so they find the files they need.
repo_root = Path(__file__).resolve().parents[1]

builder.start([planner, worker], cwd=str(repo_root))
