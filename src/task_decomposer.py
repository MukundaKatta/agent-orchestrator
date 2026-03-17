"""Decompose complex tasks into subtask DAGs."""
from typing import List
from .models import SubTask, TaskGraph, AgentCapability
import logging, re

logger = logging.getLogger(__name__)

CAPABILITY_KEYWORDS = {
    AgentCapability.RESEARCH: ["search", "find", "research", "look up", "investigate"],
    AgentCapability.CODE: ["code", "implement", "build", "create", "develop", "program"],
    AgentCapability.REVIEW: ["review", "check", "verify", "validate", "audit"],
    AgentCapability.WRITE: ["write", "document", "draft", "compose", "summarize"],
    AgentCapability.ANALYZE: ["analyze", "evaluate", "assess", "compare", "measure"],
}

def infer_capabilities(description: str) -> List[AgentCapability]:
    desc_lower = description.lower()
    caps = []
    for cap, keywords in CAPABILITY_KEYWORDS.items():
        if any(kw in desc_lower for kw in keywords):
            caps.append(cap)
    return caps or [AgentCapability.ANALYZE]

def decompose_task(description: str) -> TaskGraph:
    """Decompose a task description into subtasks using heuristics."""
    sentences = [s.strip() for s in re.split(r'[.;\n]', description) if s.strip() and len(s.strip()) > 10]
    
    if not sentences:
        sentences = [description]
    
    subtasks = []
    for i, sentence in enumerate(sentences[:10]):
        caps = infer_capabilities(sentence)
        deps = [subtasks[i-1].id] if i > 0 and "then" in sentence.lower() else []
        subtasks.append(SubTask(
            description=sentence,
            required_capabilities=caps,
            dependencies=deps,
            priority=len(sentences) - i,
        ))
    
    return TaskGraph(description=description, subtasks=subtasks)
