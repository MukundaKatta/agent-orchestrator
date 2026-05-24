"""Core step-pipeline orchestrator.

One agent runs, hands a typed payload to the next agent, and so on. Each step
declares which `kind` of handoff it accepts and which `kind` it produces, so
the pipeline can validate the chain at construction time instead of failing
halfway through a run.

This module has no model calls, no network, no async. Steps are plain
synchronous callables. Real LLM-backed steps wrap an SDK call inside their
`run` method and remain free to do whatever they want with the payload.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class StepError(Exception):
    """A step refused its input handoff or failed during execution.

    Carries enough context for the pipeline runner to record where the failure
    happened without having to inspect the exception text.
    """

    def __init__(self, step_name: str, message: str, cause: Exception | None = None):
        self.step_name = step_name
        self.cause = cause
        super().__init__(f"step '{step_name}': {message}")


@dataclass(frozen=True)
class Handoff:
    """Immutable payload moving between adjacent steps.

    A handoff has a `kind` (a short string tag like "topic", "research_brief",
    "draft") and arbitrary `data`. `kind` is the contract: a step that accepts
    `"research_brief"` must receive a handoff whose `kind` equals
    `"research_brief"` or the pipeline raises a `StepError` before running it.

    `meta` is a free-form bag for things like model name, token count, a
    timestamp, a confidence score. The pipeline runner does not inspect it.
    """

    kind: str
    data: Any
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    """What a step returns.

    `output` is the handoff that flows to the next step. `latency_ms` is the
    wall-clock time the step spent inside its `run` method. `notes` is a
    free-form string the step writer can use for debugging or for the final
    pipeline summary.
    """

    output: Handoff
    latency_ms: float = 0.0
    notes: str = ""


@runtime_checkable
class Step(Protocol):
    """The contract every step in a pipeline implements.

    `name` is used in the run record. `accepts` is the handoff `kind` this
    step requires as input. `produces` is the handoff `kind` it returns.

    `run` takes the input handoff and the running `PipelineRun` (so the step
    can read what earlier steps produced) and returns a `StepResult`.
    """

    name: str
    accepts: str
    produces: str

    def run(self, handoff: Handoff, run: "PipelineRun") -> StepResult: ...


@dataclass
class StepRecord:
    """One row in a `PipelineRun`. Captures everything that happened in a step."""

    name: str
    accepts: str
    produces: str
    input: Handoff
    output: Handoff | None
    latency_ms: float
    status: str  # "ok" or "failed"
    notes: str = ""
    error: str | None = None


@dataclass
class PipelineRun:
    """The full record of one pipeline execution.

    Carries the run id, the initial handoff the pipeline started with, every
    step record in order, and the final handoff produced by the last step (or
    `None` if the run failed).

    The runner exposes the run object to each step so a later step can look up
    what an earlier step produced by name. Avoid mutating fields outside the
    runner; the only public helper is `record_for(step_name)`.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    initial: Handoff | None = None
    records: list[StepRecord] = field(default_factory=list)
    final: Handoff | None = None
    status: str = "pending"  # pending, ok, failed
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def record_for(self, step_name: str) -> StepRecord | None:
        """Return the record for `step_name` if it ran, else `None`."""
        for r in self.records:
            if r.name == step_name:
                return r
        return None

    @property
    def total_latency_ms(self) -> float:
        return round(sum(r.latency_ms for r in self.records), 2)

    @property
    def step_count(self) -> int:
        return len(self.records)


class Pipeline:
    """A fixed sequence of steps with validated handoff contracts.

    Construction validates that adjacent step kinds line up:

        steps[i].produces == steps[i+1].accepts

    If they do not, the pipeline raises `StepError` immediately so the
    mismatch is caught at wiring time rather than during the first run.

    `Pipeline.run(initial)` executes every step in order. The first step must
    accept `initial.kind`. Each step's output becomes the next step's input.
    A failed step short-circuits the run and the `PipelineRun.status` becomes
    `"failed"`.
    """

    def __init__(self, steps: list[Step], name: str = "pipeline"):
        if not steps:
            raise StepError(step_name=name, message="pipeline must have at least one step")

        seen_names: set[str] = set()
        for step in steps:
            if step.name in seen_names:
                raise StepError(
                    step_name=step.name,
                    message=f"duplicate step name '{step.name}' in pipeline",
                )
            seen_names.add(step.name)

        for i in range(len(steps) - 1):
            produced = steps[i].produces
            expected = steps[i + 1].accepts
            if produced != expected:
                raise StepError(
                    step_name=steps[i + 1].name,
                    message=(
                        f"contract mismatch: step '{steps[i].name}' produces '{produced}', "
                        f"but next step '{steps[i + 1].name}' accepts '{expected}'"
                    ),
                )

        self.steps = steps
        self.name = name

    @property
    def accepts(self) -> str:
        """The handoff kind the first step expects to receive."""
        return self.steps[0].accepts

    @property
    def produces(self) -> str:
        """The handoff kind the last step returns."""
        return self.steps[-1].produces

    def run(self, initial: Handoff) -> PipelineRun:
        """Execute the pipeline end-to-end."""
        if initial.kind != self.accepts:
            raise StepError(
                step_name=self.steps[0].name,
                message=(
                    f"initial handoff kind '{initial.kind}' does not match "
                    f"first step's accepts kind '{self.accepts}'"
                ),
            )

        run = PipelineRun(initial=initial)
        current: Handoff = initial

        for step in self.steps:
            if current.kind != step.accepts:
                # Should never happen if construction validated correctly, but
                # we keep the runtime check so subclasses or dynamic step
                # modification get caught.
                run.records.append(
                    StepRecord(
                        name=step.name,
                        accepts=step.accepts,
                        produces=step.produces,
                        input=current,
                        output=None,
                        latency_ms=0.0,
                        status="failed",
                        error=(
                            f"got handoff kind '{current.kind}', "
                            f"expected '{step.accepts}'"
                        ),
                    )
                )
                run.status = "failed"
                run.finished_at = time.time()
                return run

            start = time.perf_counter()
            try:
                result = step.run(current, run)
            except Exception as exc:
                latency = (time.perf_counter() - start) * 1000
                run.records.append(
                    StepRecord(
                        name=step.name,
                        accepts=step.accepts,
                        produces=step.produces,
                        input=current,
                        output=None,
                        latency_ms=round(latency, 3),
                        status="failed",
                        error=str(exc),
                    )
                )
                run.status = "failed"
                run.finished_at = time.time()
                return run

            latency = result.latency_ms or (time.perf_counter() - start) * 1000

            if result.output.kind != step.produces:
                run.records.append(
                    StepRecord(
                        name=step.name,
                        accepts=step.accepts,
                        produces=step.produces,
                        input=current,
                        output=result.output,
                        latency_ms=round(latency, 3),
                        status="failed",
                        error=(
                            f"step produced handoff kind '{result.output.kind}', "
                            f"but declared produces='{step.produces}'"
                        ),
                    )
                )
                run.status = "failed"
                run.finished_at = time.time()
                return run

            run.records.append(
                StepRecord(
                    name=step.name,
                    accepts=step.accepts,
                    produces=step.produces,
                    input=current,
                    output=result.output,
                    latency_ms=round(latency, 3),
                    status="ok",
                    notes=result.notes,
                )
            )
            current = result.output

        run.final = current
        run.status = "ok"
        run.finished_at = time.time()
        return run
