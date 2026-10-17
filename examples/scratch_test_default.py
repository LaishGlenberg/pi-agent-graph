"""Launch a planner and a worker that coordinate over pi-intercom."""

from pathlib import Path

from pi_agent_graph import AgentGraphBuilder

# commonly used models by the user
MODELS = {
    "go_ds_off": ("opencode-go/deepseek-v4.1-flash", "low"),
    "ds_ds_off": ("deepseek/deepseek-flash", "off"),
}

# ================================ DEFINITIONS ====================================
# additional context shared by agents, largely stays the same between runs
SHARED_CONTEXT = "Use pi-intercom to message other agents. NEVER assume another agent can see your output. ALWAYS respond with pi-intercom before ending your response. If you do not do this the other agent will stay waiting on you FOREVER and YOU will be responsible for breaking the entire flow"

# loads these predefined agents from pi-cli config
# AGENT_COMMANDS = {
#     "planner": "default_agent_isolated",
#     "worker": "default_agent_isolated"
# }

# models and thinking levels for agents
AGENT_MODELS = {
    "planner": MODELS["ds_ds_off"],
    "worker": MODELS["ds_ds_off"]
}

SHARED_GOAL = "This is a quick smoke test of your orchestration capabilities, the planner should create a mock plan for a mock problem, and give this to the worker who returns a mock solution. It can be a simple scenario with only a few minor tasks to check off (not multiple groups of tasks like a real feature request). Since this is a mock test you are fully isolated from actual code, you wont have access to any bash tools or actually be able to commit/test anything, all of this can just be mocked textually in the chat area. DO NOT add more than 1 task grouping"
SCENARIO = "checklist_iteration"
PROMPT = "Start working on the plan and make the checklist, when you're ready tell the worker to get started"

# ================================ BUILD AGENTS ====================================

builder = AgentGraphBuilder()

builder.set_shared_context(SHARED_CONTEXT)
builder.set_shared_goal(SHARED_GOAL)

agentList = builder.get_scenario(SCENARIO).get_agents()
loader = builder.get_agent_loader()

for agent in agentList:
    #agent.set_command(loader.get(AGENT_COMMANDS[agent.get_name()]))
    agent.set_extensions('pi-intercom')
    agent.set_skills('pi-intercom')
    agent.use_tools.set(False)
    agent.use_context.set(False)

    model, thinking = AGENT_MODELS[agent.get_name()]
    agent.set_model(model, thinking)

    print(f"Command [{agent.get_name()}]: {agent.display_command()} \n")

planner, worker = agentList

planner.set_prompt(PROMPT)

# ================================ START AGENTS ====================================
# Start both agents in the repo root so they find the files they need.
repo_root = Path(__file__).resolve().parents[1]

builder.start([planner, worker], cwd=str(repo_root))
