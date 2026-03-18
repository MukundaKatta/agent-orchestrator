"""Tests for AgentOrchestrator."""
from src.core import AgentOrchestrator
def test_init(): assert AgentOrchestrator().get_stats()["ops"] == 0
def test_op(): c = AgentOrchestrator(); c.process(x=1); assert c.get_stats()["ops"] == 1
def test_multi(): c = AgentOrchestrator(); [c.process() for _ in range(5)]; assert c.get_stats()["ops"] == 5
def test_reset(): c = AgentOrchestrator(); c.process(); c.reset(); assert c.get_stats()["ops"] == 0
def test_service_name(): c = AgentOrchestrator(); r = c.process(); assert r["service"] == "agent-orchestrator"
