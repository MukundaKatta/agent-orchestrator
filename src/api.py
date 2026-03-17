"""FastAPI application."""
from fastapi import FastAPI, HTTPException
from .models import TaskSubmission, AgentInfo, AgentCapability
from .orchestrator import Orchestrator
from .agent_registry import AgentRegistry
from .task_decomposer import decompose_task
from .human_gate import HumanGate

app = FastAPI(title="Agent Orchestrator", version="0.1.0")
registry = AgentRegistry()
gate = HumanGate()
orchestrator = Orchestrator(registry)

# Register default agents
for name, caps in [("researcher", [AgentCapability.RESEARCH, AgentCapability.ANALYZE]),
                    ("coder", [AgentCapability.CODE, AgentCapability.REVIEW]),
                    ("writer", [AgentCapability.WRITE, AgentCapability.ANALYZE])]:
    registry.register(AgentInfo(name=name, capabilities=caps))

@app.get("/health")
def health():
    return {"status": "ok", "agents": registry.count}

@app.post("/tasks")
async def submit_task(submission: TaskSubmission):
    graph = decompose_task(submission.description)
    result = await orchestrator.execute(graph, policy=submission.execution_policy)
    return result

@app.get("/agents")
def list_agents():
    return [a.model_dump() for a in registry.list_all()]

@app.post("/agents")
def register_agent(agent: AgentInfo):
    registry.register(agent)
    return {"status": "registered", "name": agent.name}

@app.get("/tasks/{task_id}/trace")
def get_trace(task_id: str):
    traces = [t for t in orchestrator.traces if t.task_id == task_id]
    return [t.model_dump() for t in traces]

@app.post("/tasks/{task_id}/approve")
def approve_task(task_id: str):
    if gate.approve(task_id):
        return {"status": "approved"}
    raise HTTPException(404, "No pending approval for this task")
