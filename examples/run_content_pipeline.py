"""End-to-end run of the example content pipeline.

Researcher -> Analyst -> Writer -> Editor, using deterministic fake agents.
No API keys, no network, no async. The point is to show the handoff
contracts wiring up and the run record threading through every step.

Run it from the repo root:

    python examples/run_content_pipeline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the in-repo `src` package importable without an install step.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents import AnalystStep, EditorStep, ResearcherStep, WriterStep
from src.pipeline import Handoff, Pipeline


def main() -> int:
    pipeline = Pipeline(
        steps=[
            ResearcherStep(bullets_per_topic=4),
            AnalystStep(),
            WriterStep(),
            EditorStep(),
        ],
        name="content-pipeline",
    )

    topic = "prompt caching for LLM apps"
    run = pipeline.run(Handoff(kind="topic", data=topic))

    print(f"pipeline:        {pipeline.name}")
    print(f"run id:          {run.id}")
    print(f"status:          {run.status}")
    print(f"steps:           {run.step_count}")
    print(f"total latency:   {run.total_latency_ms} ms")
    print()

    for r in run.records:
        marker = "ok" if r.status == "ok" else "FAIL"
        print(f"  [{marker}] {r.name:<10} {r.accepts:>16} -> {r.produces:<16} {r.latency_ms:.3f} ms")
        if r.notes:
            print(f"         notes: {r.notes}")
        if r.error:
            print(f"         error: {r.error}")
    print()

    if run.status == "ok" and run.final is not None:
        print("final post:")
        print(json.dumps(run.final.data, indent=2))
        return 0

    print("pipeline failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
