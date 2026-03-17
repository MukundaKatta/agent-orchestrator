"""Core orchestration engine."""
import asyncio, time, logging
from typing import Dict, List, Optional
from .models import TaskGraph, SubTask, TaskStatus, ExecutionTrace, Message
from .agent_registry import AgentRegistry

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.traces: List[ExecutionTrace] = []
        self.messages: List[Message] = []
        self._results: Dict[str, any] = {}

    async def execute(self, graph: TaskGraph, policy: str = "parallel") -> Dict:
        logger.info(f"Executing task graph {graph.id} with {len(graph.subtasks)} subtasks")
        
        if policy == "sequential":
            return await self._execute_sequential(graph)
        return await self._execute_parallel(graph)

    async def _execute_parallel(self, graph: TaskGraph) -> Dict:
        pending = {st.id: st for st in graph.subtasks}
        completed = set()
        results = {}

        while pending:
            ready = [st for st in pending.values()
                     if all(dep in completed for dep in st.dependencies)]
            
            if not ready:
                if pending:
                    logger.error("Deadlock detected in task graph")
                    break
                break
            
            tasks = [self._execute_subtask(st) for st in ready]
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for st, result in zip(ready, task_results):
                if isinstance(result, Exception):
                    st.status = TaskStatus.FAILED
                    results[st.id] = {"error": str(result)}
                else:
                    st.status = TaskStatus.COMPLETED
                    st.result = result
                    results[st.id] = result
                completed.add(st.id)
                del pending[st.id]
        
        return {"graph_id": graph.id, "results": results, "traces": len(self.traces)}

    async def _execute_sequential(self, graph: TaskGraph) -> Dict:
        results = {}
        for st in sorted(graph.subtasks, key=lambda s: s.priority, reverse=True):
            try:
                result = await self._execute_subtask(st)
                st.status = TaskStatus.COMPLETED
                st.result = result
                results[st.id] = result
            except Exception as e:
                st.status = TaskStatus.FAILED
                results[st.id] = {"error": str(e)}
        return {"graph_id": graph.id, "results": results}

    async def _execute_subtask(self, subtask: SubTask) -> Dict:
        start = time.time()
        agent = self.registry.find_best_agent(subtask.required_capabilities)
        
        if not agent:
            raise RuntimeError(f"No agent available for capabilities: {subtask.required_capabilities}")
        
        subtask.assigned_agent = agent.name
        subtask.status = TaskStatus.RUNNING
        
        # Simulate agent execution
        await asyncio.sleep(0.1)
        result = {"agent": agent.name, "task": subtask.description, "status": "completed"}
        
        elapsed = (time.time() - start) * 1000
        self.traces.append(ExecutionTrace(
            task_id=subtask.id, agent=agent.name,
            input_data=subtask.description, output_data=result,
            latency_ms=elapsed
        ))
        
        return result
