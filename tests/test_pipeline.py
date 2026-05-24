"""Tests for the core Pipeline, Step, Handoff, and PipelineRun types."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.pipeline import (
    Handoff,
    Pipeline,
    PipelineRun,
    Step,
    StepError,
    StepResult,
)


# ---------------------------------------------------------------------------
# Tiny inline steps used by these tests. Kept here so the pipeline tests do
# not depend on `src.agents`.
# ---------------------------------------------------------------------------


@dataclass
class _Upper:
    name: str = "upper"
    accepts: str = "text"
    produces: str = "loud_text"

    def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
        return StepResult(output=Handoff(kind=self.produces, data=str(handoff.data).upper()))


@dataclass
class _Exclaim:
    name: str = "exclaim"
    accepts: str = "loud_text"
    produces: str = "shouted_text"

    def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
        return StepResult(output=Handoff(kind=self.produces, data=f"{handoff.data}!"))


@dataclass
class _Wrap:
    name: str = "wrap"
    accepts: str = "shouted_text"
    produces: str = "wrapped_text"

    def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
        return StepResult(output=Handoff(kind=self.produces, data=f"<<{handoff.data}>>"))


@dataclass
class _Boom:
    name: str = "boom"
    accepts: str = "text"
    produces: str = "text"

    def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
        raise RuntimeError("kaboom")


@dataclass
class _Liar:
    """Declares produces='loud_text' but actually returns 'mystery_text'."""

    name: str = "liar"
    accepts: str = "text"
    produces: str = "loud_text"

    def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
        return StepResult(output=Handoff(kind="mystery_text", data="x"))


# ---------------------------------------------------------------------------
# Handoff & StepResult basics
# ---------------------------------------------------------------------------


def test_handoff_is_immutable():
    h = Handoff(kind="topic", data="ai")
    with pytest.raises(Exception):
        h.kind = "other"  # type: ignore[misc]


def test_handoff_meta_default_is_empty_dict():
    h = Handoff(kind="topic", data="ai")
    assert h.meta == {}


def test_step_result_defaults_to_zero_latency_and_empty_notes():
    r = StepResult(output=Handoff(kind="x", data=1))
    assert r.latency_ms == 0.0
    assert r.notes == ""


# ---------------------------------------------------------------------------
# Pipeline construction validation
# ---------------------------------------------------------------------------


def test_pipeline_rejects_empty_step_list():
    with pytest.raises(StepError):
        Pipeline(steps=[], name="empty")


def test_pipeline_rejects_duplicate_step_names():
    a = _Upper()
    b = _Upper(name="upper", accepts="loud_text", produces="loud_text")
    with pytest.raises(StepError, match="duplicate step name"):
        Pipeline(steps=[a, b])


def test_pipeline_rejects_contract_mismatch():
    a = _Upper()  # produces loud_text
    # next step expects shouted_text but a produces loud_text. Skip Exclaim
    # and go straight to Wrap to force the mismatch.
    c = _Wrap()  # accepts shouted_text
    with pytest.raises(StepError, match="contract mismatch"):
        Pipeline(steps=[a, c])


def test_pipeline_accepts_well_formed_chain():
    p = Pipeline(steps=[_Upper(), _Exclaim(), _Wrap()])
    assert p.accepts == "text"
    assert p.produces == "wrapped_text"


# ---------------------------------------------------------------------------
# Pipeline.run happy path
# ---------------------------------------------------------------------------


def test_run_executes_steps_in_order_and_threads_handoffs():
    p = Pipeline(steps=[_Upper(), _Exclaim(), _Wrap()])
    run = p.run(Handoff(kind="text", data="hello"))

    assert run.status == "ok"
    assert run.final is not None
    assert run.final.kind == "wrapped_text"
    assert run.final.data == "<<HELLO!>>"


def test_run_records_one_step_record_per_step_in_order():
    p = Pipeline(steps=[_Upper(), _Exclaim(), _Wrap()])
    run = p.run(Handoff(kind="text", data="hi"))

    assert [r.name for r in run.records] == ["upper", "exclaim", "wrap"]
    for r in run.records:
        assert r.status == "ok"
        assert r.error is None


def test_run_records_input_and_output_per_step():
    p = Pipeline(steps=[_Upper(), _Exclaim()])
    run = p.run(Handoff(kind="text", data="hi"))

    upper = run.record_for("upper")
    assert upper is not None
    assert upper.input.data == "hi"
    assert upper.output is not None
    assert upper.output.data == "HI"

    exclaim = run.record_for("exclaim")
    assert exclaim is not None
    assert exclaim.input.data == "HI"
    assert exclaim.output is not None
    assert exclaim.output.data == "HI!"


def test_run_id_is_unique_per_run():
    p = Pipeline(steps=[_Upper()])
    run_a = p.run(Handoff(kind="text", data="a"))
    run_b = p.run(Handoff(kind="text", data="b"))
    assert run_a.id != run_b.id


def test_pipeline_run_helpers_are_consistent():
    p = Pipeline(steps=[_Upper(), _Exclaim()])
    run = p.run(Handoff(kind="text", data="ok"))

    assert run.step_count == 2
    assert run.total_latency_ms >= 0.0
    assert run.record_for("upper") is not None
    assert run.record_for("does-not-exist") is None


# ---------------------------------------------------------------------------
# Pipeline.run failure paths
# ---------------------------------------------------------------------------


def test_run_rejects_initial_handoff_with_wrong_kind():
    p = Pipeline(steps=[_Upper()])
    with pytest.raises(StepError, match="initial handoff kind"):
        p.run(Handoff(kind="not_text", data="x"))


def test_run_short_circuits_on_step_exception():
    # Give _Boom the kinds it needs so it slots between Upper and Exclaim.
    boom = _Boom(accepts="loud_text", produces="loud_text")
    p = Pipeline(steps=[_Upper(), boom, _Exclaim()])
    run = p.run(Handoff(kind="text", data="hi"))

    assert run.status == "failed"
    assert run.final is None
    assert run.step_count == 2
    assert run.records[-1].status == "failed"
    assert "kaboom" in (run.records[-1].error or "")


def test_run_short_circuits_when_step_lies_about_output_kind():
    p = Pipeline(steps=[_Liar()])
    run = p.run(Handoff(kind="text", data="x"))

    assert run.status == "failed"
    assert run.records[-1].status == "failed"
    assert "produced handoff kind" in (run.records[-1].error or "")


# ---------------------------------------------------------------------------
# Step protocol
# ---------------------------------------------------------------------------


def test_concrete_step_satisfies_runtime_protocol():
    assert isinstance(_Upper(), Step)


def test_object_without_run_does_not_satisfy_protocol():
    class _NoRun:
        name = "x"
        accepts = "a"
        produces = "b"

    assert not isinstance(_NoRun(), Step)


# ---------------------------------------------------------------------------
# Steps can read earlier records via the PipelineRun
# ---------------------------------------------------------------------------


def test_step_can_read_earlier_step_record_via_run():
    @dataclass
    class _Echo:
        name: str = "echo"
        accepts: str = "loud_text"
        produces: str = "shouted_text"

        def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
            earlier = run.record_for("upper")
            assert earlier is not None
            return StepResult(
                output=Handoff(
                    kind=self.produces,
                    data=f"{earlier.output.data}/{handoff.data}",
                )
            )

    p = Pipeline(steps=[_Upper(), _Echo()])
    run = p.run(Handoff(kind="text", data="hi"))
    assert run.status == "ok"
    assert run.final is not None
    assert run.final.data == "HI/HI"
