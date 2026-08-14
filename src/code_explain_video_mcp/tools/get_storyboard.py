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

from code_explain_video_mcp.tools.schemas import StoryboardResult

if TYPE_CHECKING:
    from fastmcp import Context, FastMCP

    from code_explain_video_mcp.tools import ToolDeps

TOOL_NAME = "get_storyboard"

TOOL_DESCRIPTION = (
    "Fetch the scene-by-scene storyboard for a job as soon as it is planned, "
    "without waiting for the video render to finish."
)


async def get_storyboard(
    job_id: str,
    ctx: "Context | None" = None,
) -> StoryboardResult:
    """Return the storyboard for ``job_id``.

    Raises:
        JobNotFoundError: The id is unknown.
        StageNotReachedError: ``build_storyboard`` has not completed yet; the
            caller should poll ``get_render_status`` and retry.
    """
    raise NotImplementedError


def register(mcp: "FastMCP", deps: "ToolDeps") -> None:
    """Bind ``deps`` and register the tool as read-only."""
    raise NotImplementedError
