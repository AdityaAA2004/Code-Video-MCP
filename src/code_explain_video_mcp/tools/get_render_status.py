"""Tool 2 of 3: ``get_render_status`` — poll a job.

A pure read against the job store: it never advances the pipeline and never
blocks on a stage, so a tight polling loop stays cheap. On success it returns
the artifact as a local path and/or a served URL, because no host can play video
inline; on failure it returns the failing stage and a message the model can
relay verbatim.
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

if TYPE_CHECKING:
    from fastmcp import Context

    from code_explain_video_mcp.jobs.models import JobRecord
    from code_explain_video_mcp.tools import ToolDeps


def _artifact_for(record: "JobRecord", deps: "ToolDeps") -> RenderArtifact | None:
    """Build the artifact block, or ``None`` if there is nothing to hand back yet."""
    if record.video_path is None and record.video_url is None:
        return None

    delivery = deps.settings.delivery
    url = record.video_url
    if url is None and delivery.serve_over_http and record.video_path is not None:
        base = delivery.public_base_url or f"http://{delivery.static_host}:{delivery.static_port}"
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
