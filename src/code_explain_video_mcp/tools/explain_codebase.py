"""Tool 1 of 3: ``explain_codebase`` — start a job, return immediately.

Sequence:

1. Decide the scope (see :mod:`code_explain_video_mcp.tools.elicitation`).
2. Create a job record and workspace.
3. Hand the job to the background runner, which drives the LangGraph pipeline.
4. Return the ``job_id`` plus enough context for the host to poll intelligently.

This function must never await the pipeline. The whole point of the async job
store is that a render can take minutes while the tool call returns in
milliseconds.

Note on FastMCP 4 background tasks: FastMCP now ships a protocol-native task
extension (``@mcp.tool(task=True)`` + ``TasksExtension``), but it is negotiated
per connection and clients that do not support it fall back to *synchronous*
execution — which for a multi-minute render would block the host. The
architecture's own job store plus a ``job_id`` handle works on every client, so
that is what this tool uses. The native task extension can be layered on later
as an optimisation for capable clients without changing this contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from code_explain_video_mcp.tools.schemas import ExplainCodebaseResult

if TYPE_CHECKING:
    from fastmcp import Context, FastMCP

    from code_explain_video_mcp.tools import ToolDeps

TOOL_NAME = "explain_codebase"

TOOL_DESCRIPTION = (
    "Generate a short explainer video for a file, folder, or whole repository, "
    "tied to a stated goal. Returns a job_id immediately; poll get_render_status."
)


async def explain_codebase(
    goal: str | None = None,
    scope: str | None = None,
    root: str | None = None,
    ctx: "Context | None" = None,
) -> ExplainCodebaseResult:
    """Kick off the explainer pipeline and return a handle to it.

    Args:
        goal: What the viewer wants to understand; threaded into every scene.
        scope: Optional path or glob. Absent scope triggers the resolution
            ladder: elicit (if supported) -> attached context -> whole repo.
        root: Repo root to resolve ``scope`` against.
        ctx: Injected by FastMCP; used for elicitation, progress, and logging.

    Returns:
        The new job's id, how scope was decided, and the stage count.
    """
    raise NotImplementedError


def register(mcp: "FastMCP", deps: "ToolDeps") -> None:
    """Bind ``deps`` into the tool callable and register it with the server."""
    raise NotImplementedError
