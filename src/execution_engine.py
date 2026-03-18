"""Full execution trace logging with replay capability."""
import time, json, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class TraceEntry:
    task_id: str
    agent_name: str
    input_data: Any
    output_data: Any = None
    status: str = "started"
    latency_ms: float = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None

class ExecutionEngine:
    """Records and replays full execution traces."""

    def __init__(self, trace_dir: str = "~/.agent-orchestrator/traces"):
        self.trace_dir = Path(trace_dir).expanduser()
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self._traces: Dict[str, List[TraceEntry]] = {}

    def start_trace(self, execution_id: str) -> None:
        self._traces[execution_id] = []

    def record(self, execution_id: str, entry: TraceEntry) -> None:
        if execution_id not in self._traces:
            self._traces[execution_id] = []
        self._traces[execution_id].append(entry)
        logger.debug(f"Trace [{execution_id}]: {entry.agent_name} -> {entry.status}")

    def get_trace(self, execution_id: str) -> List[TraceEntry]:
        return self._traces.get(execution_id, [])

    def save_trace(self, execution_id: str) -> str:
        trace = self._traces.get(execution_id, [])
        path = self.trace_dir / f"{execution_id}.json"
        data = [{"task_id": e.task_id, "agent": e.agent_name, "status": e.status,
                  "latency_ms": e.latency_ms, "tokens": e.tokens_used,
                  "cost": e.cost_usd, "timestamp": e.timestamp,
                  "error": e.error} for e in trace]
        path.write_text(json.dumps(data, indent=2))
        return str(path)

    def load_trace(self, execution_id: str) -> List[Dict]:
        path = self.trace_dir / f"{execution_id}.json"
        if path.exists():
            return json.loads(path.read_text())
        return []

    def get_cost_summary(self, execution_id: str) -> Dict[str, float]:
        trace = self._traces.get(execution_id, [])
        total_cost = sum(e.cost_usd for e in trace)
        total_tokens = sum(e.tokens_used for e in trace)
        total_latency = sum(e.latency_ms for e in trace)
        return {"total_cost_usd": round(total_cost, 4),
                "total_tokens": total_tokens,
                "total_latency_ms": round(total_latency, 2),
                "num_steps": len(trace)}
