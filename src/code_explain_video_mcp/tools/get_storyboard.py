"""Tool 3 of 3: ``get_storyboard`` — read the scene plan mid-flight.

The storyboard is finished at stage 3, long before the render, and is useful on
its own: returning it early lets a user review or correct the plan while codegen
and rendering are still running. Both forms come back — the ``Storyboard`` object
that ``generate_remotion_code`` consumes, and a Markdown rendering for humans.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from code_explain_video_mcp.errors import StageNotReachedError
from code_explain_video_mcp.storyboard.markdown import render_markdown
from code_explain_video_mcp.storyboard.schema import Storyboard
from code_explain_video_mcp.tools.schemas import StoryboardResult

if TYPE_CHECKING:
    from fastmcp import Context

    from code_explain_video_mcp.tools import ToolDeps


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

    # ``JobRecord.storyboard`` is typed ``object`` to keep the job store free of
    # storyboard imports, so re-validate anything that is not already a model.
    storyboard = record.storyboard
    if not isinstance(storyboard, Storyboard):
        storyboard = Storyboard.model_validate(storyboard)

    return StoryboardResult(
        job_id=record.job_id,
        status=record.status,
        storyboard=storyboard,
        markdown=render_markdown(storyboard),
        editable=not record.storyboard_consumed,
    )
