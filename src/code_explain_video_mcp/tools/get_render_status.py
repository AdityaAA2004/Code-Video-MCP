"""Tool 2 of 3: ``get_render_status`` — poll a job.

Pure read against the job store. It never advances the pipeline and never
blocks waiting for a stage; a caller that polls in a tight loop should get a
cheap answer every time.

On success it returns the artifact as a local path and/or a served URL, because
no host can play video inline. On failure it returns the failing stage and a
message the model can relay verbatim — including the "hit the retry cap"
message from the validate/fix loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from code_explain_video_mcp.jobs.models import (
    STAGE_LABELS,
    TOTAL_STAGES,
    stage_index,
    stage_progress,
)
from code_explain_video_mcp.tools.schemas import RenderArtifact, RenderStatusResult

# Runtime import: see the note in ``explain_codebase`` — FastMCP evaluates tool
# annotations at registration time.
from fastmcp import Context

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from code_explain_video_mcp.jobs.models import JobRecord
    from code_explain_video_mcp.tools import ToolDeps

TOOL_NAME = "get_render_status"

TOOL_DESCRIPTION = (
    "Check progress of an explainer video job. Returns the current stage, a "
    "progress estimate, and the video path or URL once rendering completes."
)


def _artifact_for(record: "JobRecord", deps: "ToolDeps") -> RenderArtifact | None:
    """Build the artifact block, or ``None`` if there is nothing to hand back yet."""
    if record.video_path is None and record.video_url is None:
        return None

    url = record.video_url
    if url is None and deps.settings.delivery.serve_over_http and record.video_path is not None:
        base = deps.settings.delivery.public_base_url or (
            f"http://{deps.settings.delivery.static_host}:{deps.settings.delivery.static_port}"
        )
        url = f"{base.rstrip('/')}/{record.job_id}/{record.video_path.name}"

    return RenderArtifact(
        local_path=str(record.video_path) if record.video_path else None,
        url=url,
        duration_seconds=record.video_duration_seconds,
        size_bytes=record.video_size_bytes,
    )


async def get_render_status(
    deps: "ToolDeps",
    job_id: str,
    ctx: "Context | None" = None,
) -> RenderStatusResult:
    """Return the current stage, progress, or final result for ``job_id``.

    Raises:
        JobNotFoundError: The id is unknown or its record has been reaped.
    """
    record = await deps.store.get(job_id)

    message = record.message or STAGE_LABELS.get(record.stage)
    if record.status == "succeeded" and record.notes:
        # Notes carry things the model must relay verbatim (scope was defaulted,
        # the repo was sampled, this was a dry run). Fold them into the message
        # so they survive even if the host ignores the notes field.
        message = f"{message} — {' '.join(record.notes)}"

    return RenderStatusResult(
        job_id=record.job_id,
        status=record.status,
        stage=record.stage,
        stage_index=stage_index(record.stage),
        total_stages=TOTAL_STAGES,
        progress=1.0 if record.status == "succeeded" else stage_progress(record.stage),
        message=message,
        retry_count=record.retry_count,
        storyboard_available=record.storyboard_available,
        artifact=_artifact_for(record, deps),
        error=record.error,
    )


def register(mcp: "FastMCP", deps: "ToolDeps") -> None:
    """Bind ``deps`` and register the tool as read-only (idempotent, no side effects)."""
    from fastmcp.tools import Tool
    from mcp.types import ToolAnnotations

    async def tool(job_id: str, ctx: "Context | None" = None) -> RenderStatusResult:
        return await get_render_status(deps, job_id=job_id, ctx=ctx)

    tool.__doc__ = get_render_status.__doc__
    mcp.add_tool(
        Tool.from_function(
            tool,
            name=TOOL_NAME,
            description=TOOL_DESCRIPTION,
            annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        )
    )
