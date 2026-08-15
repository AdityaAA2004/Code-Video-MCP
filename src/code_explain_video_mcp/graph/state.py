"""The single state object threaded through every pipeline node.

The architecture doc names the fields this must carry: ``scope``, ``goal``,
``context_chunks``, ``storyboard``, ``remotion_code``, ``validation_errors``,
``retry_count``, ``job_id``, ``status``. They are all here, plus the few pieces
of plumbing (workspace, root, notes) that nodes need in order to do real work.

It is a ``TypedDict`` with ``total=False`` because LangGraph nodes return
*partial* updates: a node returns only the keys it touched and LangGraph merges
them. Declaring every key optional is what makes that merge type-check.

Nothing in this module imports MCP. The graph must stay runnable from a test or
a script with no server around it.
"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated, Any, TypedDict

from code_explain_video_mcp.jobs.models import JobStage


class PipelineState(TypedDict, total=False):
    """State shared by every node in the graph.

    Note the two ``Annotated[..., operator.add]`` reducers: ``notes`` and
    ``stage_log`` accumulate across nodes instead of being overwritten, so each
    node can append without having to read-modify-write the whole list.
    """

    job_id: str
    """Ties graph execution back to the record in the job store."""

    root: Path
    """Repo root that ``scope`` is resolved against."""

    goal: str | None
    """The user's stated goal, verbatim. Threaded into every scene."""

    requested_scope: str | None
    """Raw scope string as the host gave it; ``None`` means whole repo."""

    scope: Any
    """``context.scope.ResolvedScope`` — the bounded file list, after stage 1."""

    context_chunks: list[Any]
    """``context.chunking.ContextChunk`` list produced by stage 2."""

    storyboard: Any
    """``storyboard.schema.Storyboard`` produced by stage 3."""

    remotion_code: Any
    """``remotion.codegen.GeneratedCode`` produced by stage 4."""

    validation_errors: list[str]
    """``tsc``/eslint diagnostics from stage 5. Empty means the project compiles."""

    retry_count: int
    """How many times ``fix_errors`` has run. Capped by ``max_fix_retries``."""

    workspace: Any
    """``jobs.workspace.Workspace`` for this job."""

    stage: JobStage
    """The node currently executing; mirrored into the job store for polling."""

    status: str
    """``queued`` / ``running`` / ``succeeded`` / ``failed``."""

    video_path: Path | None
    """Set by stage 7 on success."""

    video_url: str | None
    """Set when delivery serves the artifact over HTTP."""

    error: str | None
    """Terminal failure message, shaped for the host to relay verbatim."""

    notes: Annotated[list[str], operator.add]
    """User-facing caveats accumulated across nodes (truncation, defaults, ...)."""

    stage_log: Annotated[list[str], operator.add]
    """Human-readable trace of what each node did. Surfaced in the job log."""


def initial_state(
    *,
    job_id: str,
    root: Path,
    goal: str | None,
    requested_scope: str | None,
    workspace: Any,
    notes: list[str] | None = None,
) -> PipelineState:
    """Build the state a job starts from.

    Every accumulator is seeded to an empty list rather than left absent —
    LangGraph's ``operator.add`` reducer needs something to add onto.
    """
    return PipelineState(
        job_id=job_id,
        root=root,
        goal=goal,
        requested_scope=requested_scope,
        workspace=workspace,
        scope=None,
        context_chunks=[],
        storyboard=None,
        remotion_code=None,
        validation_errors=[],
        retry_count=0,
        stage="queued",
        status="running",
        video_path=None,
        video_url=None,
        error=None,
        notes=list(notes or []),
        stage_log=[],
    )
