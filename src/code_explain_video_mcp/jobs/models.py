"""Job record types and the canonical stage list.

The stage vocabulary lives here rather than in ``graph`` because two very
different consumers need it: LangGraph node names, and the host-facing progress
numbers reported by ``get_render_status``. Keeping one ordered tuple means the
node names and the progress bar can never drift apart.

``JobRecord`` is a mutable snapshot of one job. The store owns the locking; the
record itself is a plain dataclass so the graph can update it cheaply between
nodes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, get_args

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]

JobStage = Literal[
    "queued",
    "resolve_scope",
    "gather_context",
    "build_storyboard",
    "generate_remotion_code",
    "validate_syntax",
    "fix_errors",
    "render_video",
    "complete",
]

PIPELINE_STAGES: tuple[JobStage, ...] = (
    "resolve_scope",
    "gather_context",
    "build_storyboard",
    "generate_remotion_code",
    "validate_syntax",
    "render_video",
)
"""The stages a host should size its progress bar against.

``fix_errors`` is deliberately absent: it is a *repair* loop that may run zero
to ``max_fix_retries`` times, so counting it would make progress go backwards.
It is still reported as the current stage while it runs.
"""

TOTAL_STAGES: int = len(PIPELINE_STAGES)

TERMINAL_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})

STAGE_LABELS: dict[JobStage, str] = {
    "queued": "Waiting to start",
    "resolve_scope": "Deciding which files to explain",
    "gather_context": "Reading the relevant code",
    "build_storyboard": "Planning the scenes",
    "generate_remotion_code": "Writing the Remotion composition",
    "validate_syntax": "Type-checking the generated code",
    "fix_errors": "Repairing type errors",
    "render_video": "Rendering the video",
    "complete": "Done",
}


def stage_index(stage: JobStage) -> int:
    """Return the 0-based index of ``stage`` in :data:`PIPELINE_STAGES`.

    Stages outside the countable pipeline map to a sensible bound: ``queued`` to
    0, ``complete`` to :data:`TOTAL_STAGES`, and ``fix_errors`` to the index of
    ``validate_syntax`` it is repairing.
    """
    if stage == "queued":
        return 0
    if stage == "complete":
        return TOTAL_STAGES
    if stage == "fix_errors":
        return PIPELINE_STAGES.index("validate_syntax")
    return PIPELINE_STAGES.index(stage)


def stage_progress(stage: JobStage) -> float:
    """Coarse 0..1 completion estimate for ``stage``."""
    return round(min(1.0, stage_index(stage) / TOTAL_STAGES), 4)


@dataclass(slots=True)
class JobRecord:
    """Everything known about one job, as the store holds it.

    Mutated in place by the runner under the store's lock. Readers get a copy
    (:meth:`snapshot`) so a poll can never observe a half-applied update.
    """

    job_id: str
    goal: str | None
    requested_scope: str | None
    root: Path
    scope_mode: str
    scope_summary: str

    status: JobStatus = "queued"
    stage: JobStage = "queued"
    message: str | None = None
    retry_count: int = 0

    storyboard: object | None = None
    """A ``Storyboard`` once ``build_storyboard`` completes; ``None`` before."""

    storyboard_consumed: bool = False
    """Set when codegen reads the storyboard — after this, edits are pointless."""

    video_path: Path | None = None
    video_url: str | None = None
    video_duration_seconds: float | None = None
    video_size_bytes: int | None = None

    error: str | None = None
    notes: list[str] = field(default_factory=list)
    workspace: Path | None = None

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    stage_history: list[tuple[str, float]] = field(default_factory=list)
    """``(stage, monotonic-ish timestamp)`` pairs, for the job log and debugging."""

    @property
    def is_terminal(self) -> bool:
        """Whether the job has stopped moving (succeeded, failed, or cancelled)."""
        return self.status in TERMINAL_STATUSES

    @property
    def storyboard_available(self) -> bool:
        """True once ``build_storyboard`` has produced something to return."""
        return self.storyboard is not None

    def touch(self) -> None:
        """Bump ``updated_at``; called on every mutation."""
        self.updated_at = time.time()

    def enter_stage(self, stage: JobStage, message: str | None = None) -> None:
        """Advance to ``stage``, recording it in the history."""
        self.stage = stage
        self.message = message if message is not None else STAGE_LABELS.get(stage)
        self.stage_history.append((stage, time.time()))
        if self.status == "queued":
            self.status = "running"
        self.touch()

    def snapshot(self) -> "JobRecord":
        """Return a shallow copy safe to hand to a reader outside the lock."""
        from copy import copy

        clone = copy(self)
        clone.notes = list(self.notes)
        clone.stage_history = list(self.stage_history)
        return clone


def is_job_stage(value: str) -> bool:
    """Whether ``value`` is a member of the :data:`JobStage` literal."""
    return value in get_args(JobStage)
