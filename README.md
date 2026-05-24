# agent-orchestrator

A small step-pipeline orchestrator for chaining AI agents, with typed handoff
contracts between adjacent steps. Pure Python, no model API, zero runtime
dependencies. v0.2.0.

## What it does

You write a list of steps. Each step declares the kind of payload it accepts
and the kind it produces. `Pipeline` validates the chain at construction
time, then runs the steps in order, threading one step's output into the
next step's input.

```python
from src.agents import AnalystStep, EditorStep, ResearcherStep, WriterStep
from src.pipeline import Handoff, Pipeline

pipeline = Pipeline(
    steps=[
        ResearcherStep(bullets_per_topic=4),
        AnalystStep(),
        WriterStep(),
        EditorStep(),
    ],
    name="content-pipeline",
)

run = pipeline.run(Handoff(kind="topic", data="prompt caching"))
print(run.status)              # "ok"
print(run.final.data["title"])  # "On prompt caching"
```

The handoff kinds wire the steps together:

| Step       | accepts          | produces         |
|------------|------------------|------------------|
| Researcher | `topic`          | `research_brief` |
| Analyst    | `research_brief` | `analysis`       |
| Writer     | `analysis`       | `draft`          |
| Editor     | `draft`          | `final_post`     |

If you wire a step that produces `analysis` directly into one that accepts
`draft`, `Pipeline(...)` raises `StepError` immediately. You do not get a
half-run that explodes three steps in.

## Why typed handoffs

Most "multi-agent" scaffolds pass dictionaries around and trust each step
to find its keys. That works until step three swaps a field name and step
five silently keeps going on stale data.

A typed handoff is a tiny contract: one string `kind` tag and a `data`
payload. Two adjacent steps must agree on the `kind`, or the pipeline
refuses to start. The check is cheap, the failure message is precise, and
the steps stay independent.

## Install

```bash
git clone https://github.com/MukundaKatta/agent-orchestrator.git
cd agent-orchestrator
pip install -e ".[dev]"
```

Python 3.10+. No runtime dependencies.

## Run the example

```bash
python examples/run_content_pipeline.py
```

Output looks like:

```
pipeline:        content-pipeline
run id:          d243c6fd2f31
status:          ok
steps:           4
total latency:   0.02 ms

  [ok] researcher            topic -> research_brief   0.005 ms
         notes: gathered 4 bullets
  [ok] analyst      research_brief -> analysis         0.004 ms
         notes: distilled 4 points
  [ok] writer             analysis -> draft            0.005 ms
         notes: wrote 39 words
  [ok] editor                draft -> final_post       0.003 ms
         notes: proofread and titled

final post:
{
  "title": "On prompt caching for LLM apps",
  "body": "Brief on prompt caching for LLM apps: fact 1 about prompt caching for LLM apps; ...",
  "word_count": 39
}
```

The four example steps are deterministic stand-ins for real LLM agents.
They show what the contracts and the run record look like without burning
any tokens. To plug in a real model, replace the body of `run` on the step;
keep `accepts` and `produces` the same.

## Public API

```python
from src import (
    Handoff,       # immutable payload between steps
    Pipeline,      # validates and runs the chain
    PipelineRun,   # full record of one execution
    Step,          # protocol every step implements
    StepError,     # raised on contract or run failure
    StepRecord,    # one row per step in a run
    StepResult,    # what a step returns from .run()
)
```

A step is anything with these three attributes and one method:

```python
@dataclass
class MyStep:
    name: str = "my-step"
    accepts: str = "input_kind"
    produces: str = "output_kind"

    def run(self, handoff: Handoff, run: PipelineRun) -> StepResult:
        ...
        return StepResult(output=Handoff(kind=self.produces, data=...))
```

That is the whole interface. No registration, no decorators, no base class.

## Scope on purpose

This v0.2.0 only does one thing: linear pipelines with typed handoffs. It
does not do DAGs, parallel fan-out, retries, message buses, human approval
gates, or model API calls. The v0.1 scaffold tried to ship all of those at
once and finished none of them. This release picks the one pattern that
actually runs end-to-end and pins it with tests.

## Tests

```bash
pytest tests/ -v
```

29 tests, all passing in well under a second. No network, no API keys.

## License

MIT
