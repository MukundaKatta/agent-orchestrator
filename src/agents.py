"""Example step implementations for the pipeline.

These are deterministic stand-ins for real LLM agents. They take the same
shape a real step would (Step protocol from `pipeline`) and let you exercise
the whole pipeline with zero external calls and zero API keys.

To plug in a real model, replace the body of `run` with an SDK call. The
handoff contracts (`accepts`, `produces`) stay the same.
"""

from __future__ import annotations

from dataclasses import dataclass

from .pipeline import Handoff, PipelineRun, StepResult


@dataclass
class ResearcherStep:
    """Turns a `topic` handoff into a `research_brief`.

    A real implementation would search the web, call a retrieval API, or
    prompt a long-context model. The fake version returns a small structured
    brief built from the topic string so downstream steps have something
    realistic to operate on.
    """

    name: str = "researcher"
    accepts: str = "topic"
    produces: str = "research_brief"
    bullets_per_topic: int = 3

    def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
        topic = str(handoff.data).strip()
        if not topic:
            raise ValueError("researcher: empty topic")

        bullets = [f"fact {i + 1} about {topic}" for i in range(self.bullets_per_topic)]
        brief = {
            "topic": topic,
            "bullets": bullets,
            "source_count": self.bullets_per_topic,
        }
        return StepResult(
            output=Handoff(
                kind=self.produces,
                data=brief,
                meta={"source": "fake-researcher"},
            ),
            notes=f"gathered {self.bullets_per_topic} bullets",
        )


@dataclass
class AnalystStep:
    """Turns a `research_brief` into an `analysis`.

    A real implementation would summarize, score sources, find contradictions,
    or extract entities. The fake version groups bullets, counts them, and
    attaches a stub confidence number.
    """

    name: str = "analyst"
    accepts: str = "research_brief"
    produces: str = "analysis"

    def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
        brief = handoff.data
        if not isinstance(brief, dict) or "bullets" not in brief:
            raise ValueError("analyst: expected dict brief with 'bullets'")

        bullets = list(brief.get("bullets", []))
        analysis = {
            "topic": brief.get("topic", ""),
            "key_points": bullets,
            "point_count": len(bullets),
            "confidence": 0.5 + 0.1 * min(len(bullets), 5),
        }
        return StepResult(
            output=Handoff(kind=self.produces, data=analysis),
            notes=f"distilled {len(bullets)} points",
        )


@dataclass
class WriterStep:
    """Turns an `analysis` into a `draft`.

    A real implementation would prompt a model with style guidance, a target
    length, and possibly a few-shot prompt. The fake version writes a short
    paragraph by joining key points.
    """

    name: str = "writer"
    accepts: str = "analysis"
    produces: str = "draft"

    def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
        analysis = handoff.data
        topic = analysis.get("topic", "")
        points = analysis.get("key_points", [])
        if not points:
            text = f"No content available for {topic}."
        else:
            joined = "; ".join(points)
            text = f"Brief on {topic}: {joined}."

        draft = {
            "topic": topic,
            "text": text,
            "word_count": len(text.split()),
        }
        return StepResult(
            output=Handoff(kind=self.produces, data=draft),
            notes=f"wrote {len(text.split())} words",
        )


@dataclass
class EditorStep:
    """Turns a `draft` into a `final_post`.

    A real implementation would proofread, enforce a style guide, and fix the
    title. The fake version trims whitespace, caps trailing periods, and
    builds a fixed title.
    """

    name: str = "editor"
    accepts: str = "draft"
    produces: str = "final_post"
    max_title_length: int = 80

    def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
        draft = handoff.data
        topic = draft.get("topic", "untitled")
        text = (draft.get("text") or "").strip()
        if text and not text.endswith("."):
            text = text + "."

        title = f"On {topic}"
        if len(title) > self.max_title_length:
            title = title[: self.max_title_length - 1] + "…"

        post = {
            "title": title,
            "body": text,
            "word_count": len(text.split()),
        }
        return StepResult(
            output=Handoff(kind=self.produces, data=post),
            notes="proofread and titled",
        )


@dataclass
class FailingStep:
    """A step that always raises. Useful for tests of error short-circuit.

    Configure `accepts`/`produces` to slot into any test pipeline shape.
    """

    name: str = "boom"
    accepts: str = "topic"
    produces: str = "topic"
    message: str = "intentional failure"

    def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
        raise RuntimeError(self.message)
