"""Launch a planner and a worker that coordinate over pi-intercom."""

from pathlib import Path

from pi_agent_graph import AgentGraphBuilder

# additional context shared by agents, largely stays the same between runs
SHARED_CONTEXT = "Use pi-intercom to message other agents. Never assume another agent can see your output."

# loads these predefined agents from pi-cli config
# A1_COMMAND =
# A2_COMMAND =
AGENT_COMMANDS = ["planner_example", "worker_example"]

# models and thinking levels for agents
# A1_MODEL =
# A2_MODEL =
AGENT_MODELS = [
    ("opencode-go/deepseek-v4.1-flash", "high"),
    ("opencode-go/deepseek-v4.1-flash", "off"),
]

SHARED_GOAL = "add a feature where we can define stuff like shared context, the agent command names, the prompt, as fixtures and then load them in easily, make sure each one has an identifier or name. Then in the examples/ file I can use that to load everything. I guess I could use something like planner, worker = builder.load_saved('identifier').get_agents() that backfills the builder fields and loads the updated planner and worker agents so we can start them immediately"
SCENARIO = "checklist_iteration"
PROMPT = "Start working on the plan and make the checklist, when you're ready tell the worker to get started"
# INITIATOR = "planner"

builder = AgentGraphBuilder()

builder.set_shared_context(SHARED_CONTEXT)
builder.set_shared_goal(SHARED_GOAL)

agentList = builder.get_scenario(SCENARIO).get_agents()
loader = builder.get_agent_loader()

for i, agent in enumerate(agentList):
    agent.set_command(loader.get(AGENT_COMMANDS[i]))

planner, worker = agentList

planner.set_prompt(PROMPT)

# Start both agents in the repo root so they find the files they need.
repo_root = Path(__file__).resolve().parents[1]

builder.start([planner, worker], cwd=str(repo_root))
