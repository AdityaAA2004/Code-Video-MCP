"""Tool 3 of 3: ``get_storyboard`` — read the scene plan mid-flight.

This is the escape hatch for a v1 where video generation is still flaky: the
storyboard is finished at stage 3, long before the render, and is genuinely
useful on its own. Returning it early lets a user review or correct the plan
while codegen and rendering are still running.

Returns both forms: the ``Storyboard`` object (the fixed JSON schema that
``generate_remotion_code`` consumes) and a Markdown rendering for humans.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from code_explain_video_mcp.errors import StageNotReachedError
from code_explain_video_mcp.storyboard.markdown import render_markdown
from code_explain_video_mcp.storyboard.schema import Storyboard
from code_explain_video_mcp.tools.schemas import StoryboardResult

# Runtime import: see the note in ``explain_codebase`` — FastMCP evaluates tool
# annotations at registration time.
from fastmcp import Context

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from code_explain_video_mcp.tools import ToolDeps

TOOL_NAME = "get_storyboard"

TOOL_DESCRIPTION = (
    "Fetch the scene-by-scene storyboard for a job as soon as it is planned, "
    "without waiting for the video render to finish."
)


async def get_storyboard(
    deps: "ToolDeps",
    job_id: str,
    ctx: "Context | None" = None,
) -> StoryboardResult:
    """Return the storyboard for ``job_id``.

    Raises:
        JobNotFoundError: The id is unknown.
        StageNotReachedError: ``build_storyboard`` has not completed yet; the
            caller should poll ``get_render_status`` and retry.
    """
    record = await deps.store.get(job_id)

    if record.storyboard is None:
        raise StageNotReachedError(job_id, "build_storyboard")

    storyboard = record.storyboard
    if not isinstance(storyboard, Storyboard):  # pragma: no cover - defensive
        storyboard = Storyboard.model_validate(storyboard)

    return StoryboardResult(
        job_id=record.job_id,
        status=record.status,
        storyboard=storyboard,
        markdown=render_markdown(storyboard),
        editable=not record.storyboard_consumed,
    )


def register(mcp: "FastMCP", deps: "ToolDeps") -> None:
    """Bind ``deps`` and register the tool as read-only."""
    from fastmcp.tools import Tool
    from mcp.types import ToolAnnotations

    async def tool(job_id: str, ctx: "Context | None" = None) -> StoryboardResult:
        return await get_storyboard(deps, job_id=job_id, ctx=ctx)

    tool.__doc__ = get_storyboard.__doc__
    mcp.add_tool(
        Tool.from_function(
            tool,
            name=TOOL_NAME,
            description=TOOL_DESCRIPTION,
            annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        )
    )
