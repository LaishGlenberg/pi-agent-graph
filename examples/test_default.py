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
  ("opencode-go/deepseek-v4.1-flash", "off"),
  ("opencode-go/deepseek-v4.1-flash", "off")
]

SHARED_GOAL = "This is a quick smoke test of your orchestration capabilities, the planner should create a mock plan for a mock problem, and give this to the worker who returns a mock solution"
SCENARIO = "checklist_iteration"
PROMPT = "Start working on the plan and make the checklist, when you're ready tell the worker to get started"
#INITIATOR = "planner"d

builder = AgentGraphBuilder()

builder.set_shared_context(SHARED_CONTEXT)
builder.set_shared_goal(SHARED_GOAL)

agentList = builder.get_scenario(SCENARIO).get_agents()
loader = builder.get_agent_loader()

for i, agent in enumerate(agentList):
  agent.set_command(loader.get(AGENT_COMMANDS[i]))
  model, thinking = AGENT_MODELS[i]
  agent.set_model(model, thinking)

planner, worker = agentList

planner.set_prompt(PROMPT)

# Start both agents in the repo root so they find the files they need.
repo_root = Path(__file__).resolve().parents[1]

builder.start([planner, worker], cwd=str(repo_root))
