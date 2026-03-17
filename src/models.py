"""Pydantic models for agent orchestration."""
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from enum import Enum
from datetime import datetime
import uuid

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"

class AgentCapability(str, Enum):
    RESEARCH = "research"
    CODE = "code"
    REVIEW = "review"
    WRITE = "write"
    ANALYZE = "analyze"

class SubTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    required_capabilities: List[AgentCapability]
    dependencies: List[str] = []
    priority: int = 1
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    assigned_agent: Optional[str] = None

class TaskGraph(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    subtasks: List[SubTask]
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AgentInfo(BaseModel):
    name: str
    capabilities: List[AgentCapability]
    model: str = "claude-sonnet-4-6"
    max_concurrent: int = 3
    is_available: bool = True

class Message(BaseModel):
    sender: str
    receiver: str
    task_id: str
    content: Any
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ExecutionTrace(BaseModel):
    task_id: str
    agent: str
    input_data: Any
    output_data: Any
    latency_ms: float
    tokens_used: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class TaskSubmission(BaseModel):
    description: str
    execution_policy: str = "parallel"
    require_approval: bool = False
