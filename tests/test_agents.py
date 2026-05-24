"""Tests for the example step implementations and the full demo chain."""

from __future__ import annotations

import pytest

from src.agents import (
    AnalystStep,
    EditorStep,
    FailingStep,
    ResearcherStep,
    WriterStep,
)
from src.pipeline import Handoff, Pipeline, PipelineRun


def _empty_run() -> PipelineRun:
    """An empty run object for unit-testing single steps in isolation."""
    return PipelineRun()


def test_researcher_returns_research_brief_with_expected_shape():
    step = ResearcherStep(bullets_per_topic=4)
    out = step.run(Handoff(kind="topic", data="LLM eval"), _empty_run())
    assert out.output.kind == "research_brief"
    assert out.output.data["topic"] == "LLM eval"
    assert len(out.output.data["bullets"]) == 4
    assert out.output.data["source_count"] == 4


def test_researcher_rejects_empty_topic():
    step = ResearcherStep()
    with pytest.raises(ValueError, match="empty topic"):
        step.run(Handoff(kind="topic", data="  "), _empty_run())


def test_analyst_distills_brief_into_analysis():
    brief = {"topic": "ai eval", "bullets": ["a", "b", "c"], "source_count": 3}
    out = AnalystStep().run(Handoff(kind="research_brief", data=brief), _empty_run())
    assert out.output.kind == "analysis"
    assert out.output.data["topic"] == "ai eval"
    assert out.output.data["point_count"] == 3
    assert out.output.data["key_points"] == ["a", "b", "c"]
    assert 0.5 < out.output.data["confidence"] <= 1.0


def test_analyst_rejects_non_dict_input():
    with pytest.raises(ValueError, match="expected dict brief"):
        AnalystStep().run(Handoff(kind="research_brief", data="not a dict"), _empty_run())


def test_writer_produces_draft_with_word_count():
    analysis = {
        "topic": "ai eval",
        "key_points": ["fact 1", "fact 2"],
        "point_count": 2,
        "confidence": 0.7,
    }
    out = WriterStep().run(Handoff(kind="analysis", data=analysis), _empty_run())
    assert out.output.kind == "draft"
    assert "ai eval" in out.output.data["text"]
    assert out.output.data["word_count"] > 0


def test_writer_handles_empty_points():
    analysis = {"topic": "void", "key_points": [], "point_count": 0, "confidence": 0.5}
    out = WriterStep().run(Handoff(kind="analysis", data=analysis), _empty_run())
    assert out.output.data["text"].startswith("No content")


def test_editor_caps_title_and_adds_trailing_period():
    draft = {"topic": "x", "text": "hello world", "word_count": 2}
    out = EditorStep().run(Handoff(kind="draft", data=draft), _empty_run())
    assert out.output.kind == "final_post"
    assert out.output.data["title"] == "On x"
    assert out.output.data["body"].endswith(".")


def test_editor_truncates_long_titles():
    draft = {"topic": "a" * 200, "text": "body", "word_count": 1}
    out = EditorStep(max_title_length=20).run(Handoff(kind="draft", data=draft), _empty_run())
    assert len(out.output.data["title"]) == 20


def test_full_four_step_pipeline_runs_end_to_end():
    p = Pipeline(
        steps=[
            ResearcherStep(),
            AnalystStep(),
            WriterStep(),
            EditorStep(),
        ],
        name="content-pipeline",
    )
    run = p.run(Handoff(kind="topic", data="prompt caching"))

    assert run.status == "ok"
    assert run.final is not None
    assert run.final.kind == "final_post"
    assert "prompt caching" in run.final.data["title"]
    assert run.final.data["word_count"] > 0
    assert run.step_count == 4


def test_full_pipeline_records_match_expected_handoff_kinds():
    p = Pipeline(
        steps=[ResearcherStep(), AnalystStep(), WriterStep(), EditorStep()],
    )
    run = p.run(Handoff(kind="topic", data="reliability"))

    kinds = [(r.accepts, r.produces) for r in run.records]
    assert kinds == [
        ("topic", "research_brief"),
        ("research_brief", "analysis"),
        ("analysis", "draft"),
        ("draft", "final_post"),
    ]


def test_failing_step_surfaces_error_and_stops_run():
    # FailingStep accepts/produces "topic" by default; AnalystStep wants
    # "research_brief", so configure FailingStep to slot in front of it.
    fail = FailingStep(accepts="topic", produces="research_brief", message="boom")
    p = Pipeline(steps=[fail, AnalystStep()])
    run = p.run(Handoff(kind="topic", data="x"))

    assert run.status == "failed"
    assert run.step_count == 1
    assert run.records[0].error is not None and "boom" in run.records[0].error
