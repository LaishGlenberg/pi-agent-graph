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
SHARED_CONTEXT = "Use pi-intercom to message other agents. NEVER assume another agent can see your output. ALWAYS respond with pi-intercom before ending your response. If you do not do this the other agent will stay waiting on you FOREVER and YOU will be responsible for breaking the entire flow. Use intercom terminal env IDs if there are multiple worker or planner agents"

# loads these predefined agents from pi-cli config (optional)
# AGENT_COMMANDS = {
#     "planner": "default_agent_isolated",
#     "worker": "default_agent_isolated",
#     "default": "default_agent_isolated"
# }

# models and thinking levels for agents
AGENT_MODELS = {
    "planner": MODELS["ds_ds_off"],
    "worker": MODELS["ds_ds_off"]
}

SHARED_GOAL = "This is a quick smoke test of your orchestration capabilities and to make sure intercom is working, finish execution when the test is over and no errors arose."
SCENARIO = "testing"
PROMPT = "Start off the test"

# ================================ BUILD AGENTS ====================================

builder = AgentGraphBuilder()

builder.set_shared_context(SHARED_CONTEXT)
builder.set_shared_goal(SHARED_GOAL)

agentList = builder.get_scenario(SCENARIO).get_agents()

for agent in agentList:
    agent.set_extensions('pi-intercom')
    agent.set_skills('pi-intercom')
    agent.use_tools.set(False)
    agent.use_context.set(False)

    model, thinking = AGENT_MODELS[agent.get_name()]
    agent.set_model(model, thinking)

    print(f"Command [{agent.get_name()}]: {agent.display_command()} \n")

# ------------------ Equivalent To ----------------------
#
# builder.set_extensions('pi-intercom')
# builder.set_skills('pi-intercom')
# builder.use_tools.set(False)
# builder.use_context.set(False)
# builder.set_model("deepseek/deepseek-flash", "off")
# print(f"Agent Commands:\n{builder.display_command()}\n")
#
# ---------------- Predefined Command --------------------
#
# [agent | builder].set_command(loader.get(AGENT_MODELS["default"]))
#
#---------------------------------------------------------

planner, worker = agentList

planner.set_prompt(PROMPT)

# ================================ START AGENTS ====================================
# Start both agents in the repo root so they find the files they need.
cwd_path = Path(__file__).resolve().parents[1]

# For Windows or Mac users without tmux installed you can only use layout=window,tab
builder.start([planner, worker], cwd=str(cwd_path), layout="even-horizontal")
