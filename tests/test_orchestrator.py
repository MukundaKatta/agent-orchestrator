"""Tests for orchestrator."""
import pytest, asyncio
from src.models import AgentInfo, AgentCapability, TaskSubmission
from src.agent_registry import AgentRegistry
from src.task_decomposer import decompose_task
from src.orchestrator import Orchestrator
from src.human_gate import HumanGate

@pytest.fixture
def registry():
    r = AgentRegistry()
    r.register(AgentInfo(name="researcher", capabilities=[AgentCapability.RESEARCH, AgentCapability.ANALYZE]))
    r.register(AgentInfo(name="coder", capabilities=[AgentCapability.CODE, AgentCapability.REVIEW]))
    r.register(AgentInfo(name="writer", capabilities=[AgentCapability.WRITE]))
    return r

def test_registry_register(registry):
    assert registry.count == 3

def test_registry_find_by_capability(registry):
    agents = registry.find_by_capability(AgentCapability.RESEARCH)
    assert len(agents) == 1
    assert agents[0].name == "researcher"

def test_registry_find_best_agent(registry):
    agent = registry.find_best_agent([AgentCapability.CODE, AgentCapability.REVIEW])
    assert agent.name == "coder"

def test_decompose_simple():
    graph = decompose_task("Research the topic. Write a summary.")
    assert len(graph.subtasks) == 2

def test_decompose_complex():
    graph = decompose_task("Search for ML papers. Analyze the results. Write a report. Review the report.")
    assert len(graph.subtasks) == 4

@pytest.mark.asyncio
async def test_orchestrator_execute(registry):
    orch = Orchestrator(registry)
    graph = decompose_task("Research AI trends. Write a summary.")
    result = await orch.execute(graph)
    assert "results" in result
    assert len(result["results"]) == 2

@pytest.mark.asyncio
async def test_orchestrator_sequential(registry):
    orch = Orchestrator(registry)
    graph = decompose_task("Analyze data. Write report.")
    result = await orch.execute(graph, policy="sequential")
    assert "results" in result

def test_human_gate():
    gate = HumanGate(timeout=1.0)
    assert len(gate.pending_approvals) == 0

@pytest.mark.asyncio
async def test_human_gate_approve():
    gate = HumanGate(timeout=5.0)
    async def approve_later():
        await asyncio.sleep(0.1)
        gate.approve("test-task")
    asyncio.create_task(approve_later())
    result = await gate.request_approval("test-task", "Test approval")
    assert result is True

@pytest.mark.asyncio
async def test_human_gate_timeout():
    gate = HumanGate(timeout=0.1)
    result = await gate.request_approval("test-task", "Test")
    assert result is False

def test_task_graph_structure():
    graph = decompose_task("Step one. Step two. Step three.")
    for st in graph.subtasks:
        assert st.description
        assert len(st.required_capabilities) > 0

def test_infer_capabilities():
    from src.task_decomposer import infer_capabilities
    caps = infer_capabilities("Search for information about Python")
    assert AgentCapability.RESEARCH in caps

def test_agent_info_model():
    agent = AgentInfo(name="test", capabilities=[AgentCapability.CODE])
    assert agent.is_available is True
    assert agent.model == "claude-sonnet-4-6"
