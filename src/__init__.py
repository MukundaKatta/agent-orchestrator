"""agent-orchestrator: a small step pipeline for chaining AI agents.

Public surface:
    Pipeline      - runs a list of steps with typed handoffs
    Step          - protocol every step in a pipeline implements
    Handoff       - immutable payload passed between adjacent steps
    StepResult    - what a step returns (output handoff plus metadata)
    PipelineRun   - full record of one pipeline execution
    StepError     - raised when a step refuses its input handoff
"""

from .pipeline import (
    Handoff,
    Pipeline,
    PipelineRun,
    Step,
    StepError,
    StepRecord,
    StepResult,
)

__version__ = "0.2.0"

__all__ = [
    "Handoff",
    "Pipeline",
    "PipelineRun",
    "Step",
    "StepError",
    "StepRecord",
    "StepResult",
    "__version__",
]
