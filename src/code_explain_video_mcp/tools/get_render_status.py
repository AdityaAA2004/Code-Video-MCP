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

from code_explain_video_mcp.tools.schemas import RenderStatusResult

if TYPE_CHECKING:
    from fastmcp import Context, FastMCP

    from code_explain_video_mcp.tools import ToolDeps

TOOL_NAME = "get_render_status"

TOOL_DESCRIPTION = (
    "Check progress of an explainer video job. Returns the current stage, a "
    "progress estimate, and the video path or URL once rendering completes."
)


async def get_render_status(
    job_id: str,
    ctx: "Context | None" = None,
) -> RenderStatusResult:
    """Return the current stage, progress, or final result for ``job_id``.

    Raises:
        JobNotFoundError: The id is unknown or its record has been reaped.
    """
    raise NotImplementedError


def register(mcp: "FastMCP", deps: "ToolDeps") -> None:
    """Bind ``deps`` and register the tool as read-only (idempotent, no side effects)."""
    raise NotImplementedError
