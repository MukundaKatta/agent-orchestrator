"""Per-execution cost tracking: token usage x model pricing, aggregate by agent/task/time."""
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (input/output) for common models
MODEL_PRICING: Dict[str, Tuple[float, float]] = {
    "gpt-4": (30.0, 60.0),
    "gpt-4-turbo": (10.0, 30.0),
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-3.5-turbo": (0.50, 1.50),
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku": (0.25, 1.25),
    "claude-3-haiku": (0.25, 1.25),
    "claude-3-sonnet": (3.0, 15.0),
    "claude-3-opus": (15.0, 75.0),
    "llama-3-70b": (0.59, 0.79),
    "llama-3-8b": (0.05, 0.08),
    "mistral-large": (2.0, 6.0),
    "mistral-small": (0.20, 0.60),
}


@dataclass
class TokenUsage:
    """Token usage for a single execution."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self):
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens


@dataclass
class CostEntry:
    """A single cost record."""
    execution_id: str
    agent_name: str
    task_id: str
    model: str
    usage: TokenUsage
    cost_usd: float
    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class CostSummary:
    """Aggregated cost summary."""
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_requests: int = 0
    by_agent: Dict[str, float] = field(default_factory=dict)
    by_model: Dict[str, float] = field(default_factory=dict)
    by_task: Dict[str, float] = field(default_factory=dict)
    avg_cost_per_request: float = 0.0
    avg_tokens_per_request: float = 0.0
    time_range_start: Optional[float] = None
    time_range_end: Optional[float] = None


def compute_cost(usage: TokenUsage, model: str) -> float:
    """Compute cost in USD for given token usage and model."""
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        # Try partial match
        for model_name, price in MODEL_PRICING.items():
            if model_name in model or model in model_name:
                pricing = price
                break
    if not pricing:
        logger.warning(f"No pricing for model '{model}', using default")
        pricing = (1.0, 2.0)  # Conservative default

    input_cost = (usage.input_tokens / 1_000_000) * pricing[0]
    output_cost = (usage.output_tokens / 1_000_000) * pricing[1]
    return round(input_cost + output_cost, 6)


class CostTracker:
    """Track costs across executions, agents, and time periods."""

    def __init__(self, budget_usd: Optional[float] = None):
        self._entries: List[CostEntry] = []
        self._budget_usd = budget_usd
        self._total_cost = 0.0
        self._by_agent: Dict[str, float] = defaultdict(float)
        self._by_model: Dict[str, float] = defaultdict(float)
        self._by_task: Dict[str, float] = defaultdict(float)
        self._by_execution: Dict[str, float] = defaultdict(float)

    def record(self, execution_id: str, agent_name: str, task_id: str,
               model: str, usage: TokenUsage,
               latency_ms: float = 0.0, metadata: Optional[Dict] = None) -> CostEntry:
        """Record a cost entry."""
        cost = compute_cost(usage, model)
        entry = CostEntry(
            execution_id=execution_id, agent_name=agent_name,
            task_id=task_id, model=model, usage=usage,
            cost_usd=cost, latency_ms=latency_ms,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        self._total_cost += cost
        self._by_agent[agent_name] += cost
        self._by_model[model] += cost
        self._by_task[task_id] += cost
        self._by_execution[execution_id] += cost

        if self._budget_usd and self._total_cost > self._budget_usd:
            logger.warning(
                f"Budget exceeded! Total: ${self._total_cost:.4f}, "
                f"Budget: ${self._budget_usd:.4f}"
            )

        logger.debug(
            f"Cost: {agent_name}/{model} - {usage.total_tokens} tokens = ${cost:.6f}"
        )
        return entry

    def get_execution_cost(self, execution_id: str) -> float:
        """Get total cost for a specific execution."""
        return self._by_execution.get(execution_id, 0.0)

    def get_agent_cost(self, agent_name: str) -> float:
        """Get total cost for a specific agent."""
        return self._by_agent.get(agent_name, 0.0)

    def get_summary(self, since: Optional[float] = None,
                    until: Optional[float] = None) -> CostSummary:
        """Get aggregated cost summary, optionally filtered by time range."""
        entries = self._entries
        if since:
            entries = [e for e in entries if e.timestamp >= since]
        if until:
            entries = [e for e in entries if e.timestamp <= until]

        if not entries:
            return CostSummary()

        total_cost = sum(e.cost_usd for e in entries)
        total_input = sum(e.usage.input_tokens for e in entries)
        total_output = sum(e.usage.output_tokens for e in entries)
        total_requests = len(entries)

        by_agent: Dict[str, float] = defaultdict(float)
        by_model: Dict[str, float] = defaultdict(float)
        by_task: Dict[str, float] = defaultdict(float)
        for e in entries:
            by_agent[e.agent_name] += e.cost_usd
            by_model[e.model] += e.cost_usd
            by_task[e.task_id] += e.cost_usd

        return CostSummary(
            total_cost_usd=round(total_cost, 6),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_requests=total_requests,
            by_agent=dict(sorted(by_agent.items(), key=lambda x: x[1], reverse=True)),
            by_model=dict(sorted(by_model.items(), key=lambda x: x[1], reverse=True)),
            by_task=dict(sorted(by_task.items(), key=lambda x: x[1], reverse=True)),
            avg_cost_per_request=round(total_cost / total_requests, 6),
            avg_tokens_per_request=round((total_input + total_output) / total_requests, 1),
            time_range_start=entries[0].timestamp if entries else None,
            time_range_end=entries[-1].timestamp if entries else None,
        )

    def get_daily_costs(self, days: int = 30) -> List[Dict]:
        """Get cost breakdown by day."""
        now = time.time()
        cutoff = now - (days * 86400)
        entries = [e for e in self._entries if e.timestamp >= cutoff]

        daily: Dict[str, float] = defaultdict(float)
        for e in entries:
            day = datetime.fromtimestamp(e.timestamp).strftime("%Y-%m-%d")
            daily[day] += e.cost_usd

        return [{"date": d, "cost_usd": round(c, 4)} for d, c in sorted(daily.items())]

    def check_budget(self) -> Dict:
        """Check budget status."""
        if not self._budget_usd:
            return {"budget_set": False, "total_cost": self._total_cost}
        remaining = self._budget_usd - self._total_cost
        return {
            "budget_usd": self._budget_usd,
            "spent_usd": round(self._total_cost, 4),
            "remaining_usd": round(remaining, 4),
            "utilization_pct": round(self._total_cost / self._budget_usd * 100, 1),
            "exceeded": self._total_cost > self._budget_usd,
        }

    @property
    def total_cost(self) -> float:
        return self._total_cost

    @property
    def entry_count(self) -> int:
        return len(self._entries)
