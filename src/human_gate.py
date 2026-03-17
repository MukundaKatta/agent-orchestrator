"""Human-in-the-loop approval checkpoints."""
import asyncio, logging
from typing import Dict, Optional
from .models import TaskStatus

logger = logging.getLogger(__name__)

class HumanGate:
    def __init__(self, timeout: float = 300.0):
        self.timeout = timeout
        self._pending: Dict[str, asyncio.Event] = {}
        self._decisions: Dict[str, bool] = {}

    async def request_approval(self, task_id: str, description: str) -> bool:
        logger.info(f"Approval requested for task {task_id}: {description}")
        event = asyncio.Event()
        self._pending[task_id] = event
        
        try:
            await asyncio.wait_for(event.wait(), timeout=self.timeout)
            return self._decisions.get(task_id, False)
        except asyncio.TimeoutError:
            logger.warning(f"Approval timeout for task {task_id}, defaulting to reject")
            return False
        finally:
            self._pending.pop(task_id, None)

    def approve(self, task_id: str) -> bool:
        if task_id in self._pending:
            self._decisions[task_id] = True
            self._pending[task_id].set()
            return True
        return False

    def reject(self, task_id: str) -> bool:
        if task_id in self._pending:
            self._decisions[task_id] = False
            self._pending[task_id].set()
            return True
        return False

    @property
    def pending_approvals(self):
        return list(self._pending.keys())
