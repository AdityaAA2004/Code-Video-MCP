"""Pydantic models for the three tools' inputs and outputs.

These are the contract the host sees. FastMCP derives both the input JSON Schema
and the structured output schema from these annotations, so field names,
docstrings, and ``Field`` descriptions here are prompt surface for the calling
model — they are worth wording carefully.

Kept separate from the tool bodies so tests can assert on the wire shape without
constructing a server.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from code_explain_video_mcp.jobs.models import JobStage, JobStatus
from code_explain_video_mcp.storyboard.schema import Storyboard

ScopeMode = Literal["explicit", "attached_context", "whole_repo"]


class ExplainCodebaseInput(BaseModel):
    """Arguments for ``explain_codebase``."""

    scope: str | None = Field(
        default=None,
        description=(
            "Path or glob to explain, relative to the repo root. Omit to let the "
            "server ask (when the client supports elicitation) or fall back to "
            "attached context, then the whole repo."
        ),
    )
    goal: str | None = Field(
        default=None,
        description="What the viewer wants to understand. Shapes every scene.",
    )
    root: str | None = Field(
        default=None,
        description="Repo root to resolve `scope` against. Defaults to the server's cwd.",
    )


class ExplainCodebaseResult(BaseModel):
    """Immediate response — the pipeline has only just been kicked off."""

    job_id: str
    status: JobStatus
    scope_mode: ScopeMode = Field(
        description="How scope was decided. `whole_repo` must be surfaced to the user verbatim."
    )
    resolved_scope_summary: str = Field(
        description="Human-readable description of what will be explained."
    )
    total_stages: int = Field(description="Stage count so the host can show progress.")
    poll_hint: str = Field(
        description="Instruction telling the model to poll get_render_status with the job_id."
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Caveats, e.g. that scope was defaulted or files were truncated by the cap.",
    )


class JobIdInput(BaseModel):
    """Shared input for both polling tools."""

    job_id: str = Field(description="Job id returned by explain_codebase.")


class RenderArtifact(BaseModel):
    """Where the finished video actually is.

    Hosts cannot render video inline, so this is always a path and/or a URL.
    """

    local_path: str | None = None
    url: str | None = None
    duration_seconds: float | None = None
    size_bytes: int | None = None


class RenderStatusResult(BaseModel):
    """Response for ``get_render_status``."""

    job_id: str
    status: JobStatus
    stage: JobStage
    stage_index: int
    total_stages: int
    progress: float = Field(ge=0.0, le=1.0, description="Coarse 0..1 completion estimate.")
    message: str | None = None
    retry_count: int = Field(
        default=0, description="How many times the validate/fix loop has run."
    )
    storyboard_available: bool = Field(
        default=False, description="True once build_storyboard has completed."
    )
    artifact: RenderArtifact | None = None
    error: str | None = None


class StoryboardResult(BaseModel):
    """Response for ``get_storyboard``.

    Carries both the machine-readable storyboard (the same object
    ``generate_remotion_code`` consumes) and a rendered Markdown view for the
    human in the loop to review or edit before the render lands.
    """

    job_id: str
    status: JobStatus
    storyboard: Storyboard
    markdown: str
    editable: bool = Field(
        default=False,
        description="True while codegen has not yet consumed the storyboard.",
    )
