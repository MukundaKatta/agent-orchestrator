"""Execution replay: load saved traces, re-execute, compare outputs, detect regressions."""
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ReplayStep:
    """A single step in a replay."""
    step_index: int
    task_id: str
    agent_name: str
    original_input: Any
    original_output: Any
    replay_output: Optional[Any] = None
    match: bool = True
    diff_details: str = ""
    latency_ms: float = 0.0


@dataclass
class ReplayResult:
    """Full result of replaying an execution trace."""
    execution_id: str
    total_steps: int = 0
    matched_steps: int = 0
    mismatched_steps: int = 0
    skipped_steps: int = 0
    steps: List[ReplayStep] = field(default_factory=list)
    regressions: List[str] = field(default_factory=list)
    total_time_ms: float = 0.0

    @property
    def match_rate(self) -> float:
        if self.total_steps == 0:
            return 1.0
        return self.matched_steps / self.total_steps

    @property
    def has_regressions(self) -> bool:
        return len(self.regressions) > 0


def compare_outputs(original: Any, replay: Any, tolerance: float = 1e-6) -> Tuple[bool, str]:
    """Compare two outputs for equivalence.

    Handles dicts, lists, numbers (with tolerance), and strings.
    Returns (is_match, diff_description).
    """
    if original is None and replay is None:
        return True, ""
    if type(original) != type(replay):
        return False, f"Type mismatch: {type(original).__name__} vs {type(replay).__name__}"

    if isinstance(original, dict):
        orig_keys = set(original.keys())
        rep_keys = set(replay.keys())
        if orig_keys != rep_keys:
            missing = orig_keys - rep_keys
            extra = rep_keys - orig_keys
            parts = []
            if missing:
                parts.append(f"missing keys: {missing}")
            if extra:
                parts.append(f"extra keys: {extra}")
            return False, "; ".join(parts)

        diffs = []
        for key in orig_keys:
            match, diff = compare_outputs(original[key], replay[key], tolerance)
            if not match:
                diffs.append(f"key '{key}': {diff}")
        if diffs:
            return False, "; ".join(diffs[:5])
        return True, ""

    if isinstance(original, list):
        if len(original) != len(replay):
            return False, f"List length: {len(original)} vs {len(replay)}"
        diffs = []
        for i, (o, r) in enumerate(zip(original, replay)):
            match, diff = compare_outputs(o, r, tolerance)
            if not match:
                diffs.append(f"index {i}: {diff}")
        if diffs:
            return False, "; ".join(diffs[:5])
        return True, ""

    if isinstance(original, (int, float)):
        if abs(original - replay) > tolerance:
            return False, f"Value: {original} vs {replay} (diff={abs(original - replay):.6f})"
        return True, ""

    if isinstance(original, str):
        if original != replay:
            return False, f"String: '{original[:50]}' vs '{replay[:50]}'"
        return True, ""

    # Fallback
    if original != replay:
        return False, f"Value: {original} vs {replay}"
    return True, ""


class ExecutionReplayer:
    """Replay execution traces and detect regressions."""

    def __init__(self, trace_dir: str = "~/.agent-orchestrator/traces"):
        self.trace_dir = Path(trace_dir).expanduser()
        self._executor_registry: Dict[str, Callable] = {}

    def register_executor(self, agent_name: str, executor: Callable) -> None:
        """Register an executor function for an agent.

        The executor takes input_data and returns output_data.
        """
        self._executor_registry[agent_name] = executor
        logger.info(f"Registered executor for agent: {agent_name}")

    def load_trace(self, execution_id: str) -> List[Dict]:
        """Load a saved execution trace."""
        path = self.trace_dir / f"{execution_id}.json"
        if not path.exists():
            logger.warning(f"Trace not found: {path}")
            return []
        data = json.loads(path.read_text())
        logger.info(f"Loaded trace {execution_id}: {len(data)} steps")
        return data

    def replay(self, execution_id: str, tolerance: float = 1e-6,
               dry_run: bool = False) -> ReplayResult:
        """Replay an execution trace and compare outputs.

        If dry_run=True, only loads and validates the trace without executing.
        """
        trace = self.load_trace(execution_id)
        result = ReplayResult(execution_id=execution_id, total_steps=len(trace))
        start = time.time()

        for idx, step_data in enumerate(trace):
            task_id = step_data.get("task_id", "")
            agent = step_data.get("agent", "")
            original_input = step_data.get("input", step_data.get("input_data"))
            original_output = step_data.get("output", step_data.get("output_data"))
            original_status = step_data.get("status", "completed")

            replay_step = ReplayStep(
                step_index=idx, task_id=task_id, agent_name=agent,
                original_input=original_input, original_output=original_output,
            )

            if original_status == "failed":
                replay_step.match = True
                replay_step.diff_details = "Original step failed; skipping"
                result.skipped_steps += 1
                result.steps.append(replay_step)
                continue

            if dry_run or agent not in self._executor_registry:
                replay_step.match = True
                replay_step.diff_details = "Dry run or no executor"
                result.skipped_steps += 1
                result.steps.append(replay_step)
                continue

            # Execute
            executor = self._executor_registry[agent]
            step_start = time.time()
            try:
                replay_output = executor(original_input)
                replay_step.replay_output = replay_output
                replay_step.latency_ms = (time.time() - step_start) * 1000

                match, diff = compare_outputs(original_output, replay_output, tolerance)
                replay_step.match = match
                replay_step.diff_details = diff

                if match:
                    result.matched_steps += 1
                else:
                    result.mismatched_steps += 1
                    result.regressions.append(
                        f"Step {idx} ({agent}/{task_id}): {diff}"
                    )
                    logger.warning(f"Regression at step {idx}: {diff}")

            except Exception as e:
                replay_step.match = False
                replay_step.diff_details = f"Execution error: {e}"
                result.mismatched_steps += 1
                result.regressions.append(f"Step {idx} ({agent}): execution error: {e}")

            result.steps.append(replay_step)

        result.total_time_ms = (time.time() - start) * 1000
        logger.info(
            f"Replay {execution_id}: {result.matched_steps}/{result.total_steps} matched, "
            f"{len(result.regressions)} regressions"
        )
        return result

    def compare_traces(self, trace_id_a: str, trace_id_b: str) -> Dict[str, Any]:
        """Compare two execution traces without re-executing."""
        trace_a = self.load_trace(trace_id_a)
        trace_b = self.load_trace(trace_id_b)

        diffs = []
        max_len = max(len(trace_a), len(trace_b))
        for i in range(max_len):
            if i >= len(trace_a):
                diffs.append({"step": i, "diff": "Only in trace B"})
            elif i >= len(trace_b):
                diffs.append({"step": i, "diff": "Only in trace A"})
            else:
                out_a = trace_a[i].get("output", trace_a[i].get("output_data"))
                out_b = trace_b[i].get("output", trace_b[i].get("output_data"))
                match, diff = compare_outputs(out_a, out_b)
                if not match:
                    diffs.append({"step": i, "agent": trace_a[i].get("agent", ""), "diff": diff})

        return {
            "trace_a": trace_id_a, "trace_b": trace_id_b,
            "steps_a": len(trace_a), "steps_b": len(trace_b),
            "differences": len(diffs), "details": diffs[:20],
        }
