# Changelog

All notable changes to agent-orchestrator are documented here. This project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-24

A revival release. The v0.1 scaffold tried to ship a DAG executor, a
message bus, a cost tracker, a replay engine, an LLM client, a FastAPI
surface, and a fake "AgentOrchestrator" class with eight no-op methods.
None of those pieces were wired together. v0.2.0 narrows the project to
one pattern that actually runs end-to-end.

### Added
- `Pipeline` runs a fixed list of steps in order, threading the output of
  each step into the next.
- `Handoff` is the immutable payload that flows between steps. It carries
  a string `kind` tag, the `data`, and a free-form `meta` dict.
- Adjacent steps must agree on `produces`/`accepts` kinds. Mismatches are
  caught at `Pipeline(...)` construction, not at run time.
- `PipelineRun` records every step's input, output, latency, status, and
  any error. Steps can read earlier records via `run.record_for(name)`.
- `StepResult` is what a step's `run` method returns. Carries the output
  handoff plus `latency_ms` and free-form `notes`.
- `Step` is a `runtime_checkable` Protocol. Any class with `name`,
  `accepts`, `produces`, and a matching `run` method satisfies it. No
  decorators, no base class, no registration step.
- Example steps in `src/agents.py`: `ResearcherStep`, `AnalystStep`,
  `WriterStep`, `EditorStep`. Deterministic stand-ins for real LLM agents.
- `examples/run_content_pipeline.py` runs all four steps end-to-end.
- 29 tests covering pipeline construction, run behavior, contract
  mismatches, step failures, protocol conformance, and each example step.
- MIT license. Python 3.10+. Zero runtime dependencies.

### Removed
- `src/core.py` (fake `AgentOrchestrator` with seven no-op methods that
  all returned `{"ok": True, "service": "agent-orchestrator"}`).
- `src/orchestrator.py` and `src/agent_registry.py` (capability-matching
  DAG executor that was never finished).
- `src/communication.py` (full pub/sub message bus, separate concern from
  step pipelines, not wired to the rest).
- `src/cost_tracker.py`, `src/replay.py`, `src/execution_engine.py` (three
  overlapping execution-tracking modules, none of them called by any
  other module).
- `src/llm.py` (placeholder LLM client that returned a hardcoded string).
- `src/api.py` (FastAPI surface attached to the unfinished DAG executor).
- `src/human_gate.py` (approval gate for the unfinished DAG executor).
- `src/config.py`, `src/health.py`, `src/utils.py`, `src/models.py`
  (assorted scaffold modules with no calling sites).
- `src/__main__.py` (CLI that called the fake `AgentOrchestrator`).
- `tests/test_basic.py`, `tests/test_core.py`, `tests/test_integration.py`,
  `tests/test_benchmark.py` (tested the fake `AgentOrchestrator.process`
  method, asserted things like "service name is the string we wrote in
  source").
- `tests/test_orchestrator.py`, `tests/test_communication.py`,
  `tests/test_replay.py`, `tests/test_utils.py` (tested removed modules).
- `examples/basic.py` (also had an unterminated string literal that
  prevented it from running) and `examples/advanced.py`.
- `Dockerfile`, `docker-compose.yml`, `config.example.yaml`, `.env.example`
  (served the FastAPI surface that no longer exists).
- `CONTRIBUTING.md` (claimed contributions transferred copyright to a
  third-party company that does not match the new MIT license).
- `requirements.txt` (replaced by `pyproject.toml` `dependencies`, now
  empty since there are no runtime dependencies).
- `pydantic`, `fastapi`, `uvicorn`, `anthropic`, `openai`, `numpy`
  dependencies (none of them used by the v0.2 surface).

### Changed
- License flipped from proprietary "Officethree Technologies" to MIT
  (Mukunda Katta).
- `pyproject.toml` build-backend fixed: was pointing at the non-existent
  `setuptools.backends._legacy:_Backend`, now uses
  `setuptools.build_meta`. The repo could not be installed cleanly under
  v0.1.
- Minimum Python lowered from 3.11 to 3.10.

## [0.1.0] - 2026-03-18

Initial scaffold release. Contained a multi-agent DAG executor, a
publish/subscribe message bus, a cost tracker, an execution replay
engine, an LLM client placeholder, a FastAPI service, a CLI entry
point, and a fake `AgentOrchestrator` class. None of these pieces
called each other. The repo could not be `pip install`-ed because the
build-backend reference was wrong. Last commit was 2026-03-18.
