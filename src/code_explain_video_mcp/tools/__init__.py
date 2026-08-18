"""The MCP surface: exactly three host-callable tools, registered in one place.

Each tool module exports a plain ``async def`` whose first argument is
``ToolDeps``. The thin wrappers in :func:`register_tools` drop that argument, so
the host-visible schema is only the real parameters. Registration is functional
(``mcp.add_tool``) rather than a decorator at definition, because a decorator
would bind a tool to a module-level server and defeat ``server.create_server``.

Tool bodies stay thin: validate arguments, call into ``jobs``, shape the
response. No pipeline logic here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

# Imported at runtime, not under TYPE_CHECKING: FastMCP resolves a tool's
# annotations when it is registered, so names that exist only for the type
# checker fail with ``NameError: name 'Context' is not defined`` at startup.
from fastmcp import Context

from code_explain_video_mcp.tools.schemas import (
    ExplainCodebaseResult,
    RenderStatusResult,
    StoryboardResult,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from code_explain_video_mcp.config import Settings
    from code_explain_video_mcp.jobs.runner import JobRunner
    from code_explain_video_mcp.jobs.store import JobStore

__all__ = ["ToolDeps", "register_tools"]


@dataclass(frozen=True, slots=True)
class ToolDeps:
    """Everything the three tools are allowed to touch.

    Passing this explicitly (instead of importing globals) is what makes the
    tools testable without a running server.
    """

    settings: "Settings"
    store: "JobStore"
    runner: "JobRunner"


def register_tools(mcp: "FastMCP", deps: ToolDeps) -> None:
    """Register ``explain_codebase``, ``get_render_status``, ``get_storyboard``.

    Adding a fourth registration here is a design change, not a feature: the
    architecture explicitly caps the host-visible surface at three.
    """
    from fastmcp.tools import Tool
    from mcp.types import ToolAnnotations

    from code_explain_video_mcp.tools.explain_codebase import explain_codebase
    from code_explain_video_mcp.tools.get_render_status import get_render_status
    from code_explain_video_mcp.tools.get_storyboard import get_storyboard

    async def explain_tool(
        goal: str | None = None,
        scope: str | None = None,
        root: str | None = None,
        ctx: Context | None = None,
    ) -> ExplainCodebaseResult:
        return await explain_codebase(deps, goal=goal, scope=scope, root=root, ctx=ctx)

    async def status_tool(job_id: str, ctx: Context | None = None) -> RenderStatusResult:
        return await get_render_status(deps, job_id=job_id, ctx=ctx)

    async def storyboard_tool(job_id: str, ctx: Context | None = None) -> StoryboardResult:
        return await get_storyboard(deps, job_id=job_id, ctx=ctx)

    # Both polling tools are pure reads: safe to call repeatedly, no side effects.
    read_only = ToolAnnotations(readOnlyHint=True, idempotentHint=True)

    mcp.add_tool(
        Tool.from_function(
            explain_tool,
            name="explain_codebase",
            description=(
                "Generate a short explainer video for a file, folder, or whole "
                "repository, tied to a stated goal. Returns a job_id immediately; "
                "poll get_render_status."
            ),
        )
    )
    mcp.add_tool(
        Tool.from_function(
            status_tool,
            name="get_render_status",
            description=(
                "Check progress of an explainer video job. Returns the current stage, "
                "a progress estimate, and the video path or URL once rendering completes."
            ),
            annotations=read_only,
        )
    )
    mcp.add_tool(
        Tool.from_function(
            storyboard_tool,
            name="get_storyboard",
            description=(
                "Fetch the scene-by-scene storyboard for a job as soon as it is "
                "planned, without waiting for the video render to finish."
            ),
            annotations=read_only,
        )
    )
