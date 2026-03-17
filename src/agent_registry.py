"""Agent registration and discovery."""
from typing import Dict, List, Optional
from .models import AgentInfo, AgentCapability
import logging

logger = logging.getLogger(__name__)

class AgentRegistry:
    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}

    def register(self, agent: AgentInfo) -> None:
        self._agents[agent.name] = agent
        logger.info(f"Registered agent: {agent.name} with capabilities {agent.capabilities}")

    def unregister(self, name: str) -> bool:
        if name in self._agents:
            del self._agents[name]
            return True
        return False

    def get(self, name: str) -> Optional[AgentInfo]:
        return self._agents.get(name)

    def find_by_capability(self, capability: AgentCapability) -> List[AgentInfo]:
        return [a for a in self._agents.values() if capability in a.capabilities and a.is_available]

    def find_best_agent(self, capabilities: List[AgentCapability]) -> Optional[AgentInfo]:
        candidates = self._agents.values()
        best = None
        best_score = -1
        for agent in candidates:
            if not agent.is_available:
                continue
            score = sum(1 for c in capabilities if c in agent.capabilities)
            if score > best_score:
                best_score = score
                best = agent
        return best

    def list_all(self) -> List[AgentInfo]:
        return list(self._agents.values())

    @property
    def count(self) -> int:
        return len(self._agents)
