"""Async job handling: the bridge between a fast tool call and a long pipeline.

``explain_codebase`` must return a ``job_id`` in milliseconds while the work it
started runs for minutes. That requires three cooperating pieces:

* ``models``    -- the job record and the canonical stage vocabulary.
* ``store``     -- lock-guarded shared state; snapshots for readers.
* ``workspace`` -- a directory per job for the scaffold copy, logs, and output.
* ``runner``    -- one asyncio task per job, and the guarantee that every one of
                   them ends in a terminal status.

This package knows nothing about MCP. It does import ``graph`` (the runner has
to invoke the pipeline), so the dependency direction is jobs -> graph, never the
reverse.
"""

from __future__ import annotations

from code_explain_video_mcp.jobs.models import (
    PIPELINE_STAGES,
    STAGE_LABELS,
    TOTAL_STAGES,
    JobRecord,
    JobStage,
    JobStatus,
    stage_index,
    stage_progress,
)
from code_explain_video_mcp.jobs.runner import JobRunner
from code_explain_video_mcp.jobs.store import (
    InMemoryJobStore,
    JobStore,
    build_job_record,
    new_job_id,
)
from code_explain_video_mcp.jobs.workspace import Workspace, WorkspaceManager

__all__ = [
    "PIPELINE_STAGES",
    "STAGE_LABELS",
    "TOTAL_STAGES",
    "InMemoryJobStore",
    "JobRecord",
    "JobRunner",
    "JobStage",
    "JobStatus",
    "JobStore",
    "Workspace",
    "WorkspaceManager",
    "build_job_record",
    "new_job_id",
    "stage_index",
    "stage_progress",
]
