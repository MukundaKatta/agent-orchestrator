"""Tests for execution replay."""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.replay import ExecutionReplayer, compare_outputs, ReplayResult
from src.cost_tracker import CostTracker, TokenUsage, compute_cost


class TestCompareOutputs:
    def test_equal_dicts(self):
        match, diff = compare_outputs({"a": 1, "b": 2}, {"a": 1, "b": 2})
        assert match
        assert diff == ""

    def test_different_values(self):
        match, diff = compare_outputs({"a": 1}, {"a": 2})
        assert not match
        assert "a" in diff

    def test_missing_keys(self):
        match, diff = compare_outputs({"a": 1, "b": 2}, {"a": 1})
        assert not match
        assert "missing" in diff

    def test_numeric_tolerance(self):
        match, _ = compare_outputs(1.0000001, 1.0000002, tolerance=1e-5)
        assert match

    def test_lists(self):
        match, _ = compare_outputs([1, 2, 3], [1, 2, 3])
        assert match
        match, diff = compare_outputs([1, 2], [1, 3])
        assert not match

    def test_type_mismatch(self):
        match, diff = compare_outputs(42, "42")
        assert not match
        assert "Type" in diff


class TestReplayer:
    def test_dry_run(self, tmp_path):
        import json
        trace = [
            {"task_id": "t1", "agent": "a1", "input_data": "x", "output_data": "y", "status": "completed"},
        ]
        trace_path = tmp_path / "test_exec.json"
        trace_path.write_text(json.dumps(trace))

        replayer = ExecutionReplayer(str(tmp_path))
        result = replayer.replay("test_exec", dry_run=True)
        assert result.total_steps == 1
        assert result.skipped_steps == 1
        assert not result.has_regressions

    def test_with_executor(self, tmp_path):
        import json
        trace = [
            {"task_id": "t1", "agent": "echo", "input_data": "hello", "output_data": "hello", "status": "completed"},
        ]
        (tmp_path / "exec1.json").write_text(json.dumps(trace))

        replayer = ExecutionReplayer(str(tmp_path))
        replayer.register_executor("echo", lambda x: x)
        result = replayer.replay("exec1")
        assert result.matched_steps == 1
        assert not result.has_regressions

    def test_regression_detection(self, tmp_path):
        import json
        trace = [
            {"task_id": "t1", "agent": "broken", "input_data": "in", "output_data": "expected", "status": "completed"},
        ]
        (tmp_path / "exec2.json").write_text(json.dumps(trace))

        replayer = ExecutionReplayer(str(tmp_path))
        replayer.register_executor("broken", lambda x: "different")
        result = replayer.replay("exec2")
        assert result.has_regressions
        assert result.mismatched_steps == 1


class TestCostTracker:
    def test_record_and_summary(self):
        tracker = CostTracker()
        tracker.record("exec1", "agent1", "task1", "gpt-4o", TokenUsage(1000, 500))
        tracker.record("exec1", "agent2", "task1", "gpt-4o", TokenUsage(2000, 1000))
        summary = tracker.get_summary()
        assert summary.total_requests == 2
        assert summary.total_cost_usd > 0
        assert "agent1" in summary.by_agent

    def test_budget_check(self):
        tracker = CostTracker(budget_usd=0.001)
        tracker.record("e1", "a1", "t1", "gpt-4", TokenUsage(100000, 50000))
        budget = tracker.check_budget()
        assert budget["exceeded"]

    def test_compute_cost(self):
        usage = TokenUsage(1_000_000, 1_000_000)
        cost = compute_cost(usage, "gpt-4")
        assert cost == 90.0  # $30 input + $60 output

    def test_agent_cost(self):
        tracker = CostTracker()
        tracker.record("e1", "agent_a", "t1", "gpt-4o-mini", TokenUsage(500, 200))
        tracker.record("e2", "agent_b", "t2", "gpt-4o-mini", TokenUsage(300, 100))
        assert tracker.get_agent_cost("agent_a") > 0
        assert tracker.get_agent_cost("agent_b") > 0
        assert tracker.get_agent_cost("nonexistent") == 0.0
