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

from code_explain_video_mcp.jobs.models import TOTAL_STAGES
from code_explain_video_mcp.jobs.store import build_job_record
from code_explain_video_mcp.logging_conf import get_logger
from code_explain_video_mcp.tools.elicitation import resolve_requested_scope, resolve_root
from code_explain_video_mcp.tools.schemas import ExplainCodebaseResult

# Imported at runtime, not under TYPE_CHECKING: FastMCP resolves a tool's
# annotations when it is registered, so a stringised ``Context`` that only
# exists for the type checker fails with ``NameError: name 'Context' is not
# defined`` at server startup. This module is the MCP layer, so depending on
# fastmcp here costs nothing.
from fastmcp import Context

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from code_explain_video_mcp.tools import ToolDeps

logger = get_logger("tools.explain_codebase")

TOOL_NAME = "explain_codebase"

TOOL_DESCRIPTION = (
    "Generate a short explainer video for a file, folder, or whole repository, "
    "tied to a stated goal. Returns a job_id immediately; poll get_render_status."
)


POLL_HINT = (
    "Call get_render_status with this job_id to track progress. Poll every few "
    "seconds; call get_storyboard as soon as storyboard_available is true to "
    "show the user the scene plan without waiting for the render."
)


async def explain_codebase(
    deps: "ToolDeps",
    goal: str | None = None,
    scope: str | None = None,
    root: str | None = None,
    ctx: "Context | None" = None,
) -> ExplainCodebaseResult:
    """Kick off the explainer pipeline and return a handle to it.

    Args:
        deps: Bound by :func:`register`; not part of the host-visible schema.
        goal: What the viewer wants to understand; threaded into every scene.
        scope: Optional path or glob. Absent scope triggers the resolution
            ladder: elicit (if supported) -> attached context -> whole repo.
        root: Repo root to resolve ``scope`` against.
        ctx: Injected by FastMCP; used for elicitation, progress, and logging.

    Returns:
        The new job's id, how scope was decided, and the stage count.
    """
    # Root first: if it cannot be determined, fail here rather than creating a
    # job that renders a video about whatever directory the host launched from.
    root_decision = resolve_root(root, deps.settings.default_root)
    repo_root = root_decision.root

    decision = await resolve_requested_scope(
        scope, ctx, allow_elicitation=deps.settings.allow_elicitation
    )

    notes = [*root_decision.notes, *decision.notes]
    if deps.settings.dry_run:
        notes.append(
            "This server is running in DRY RUN mode: the pipeline executes every "
            "stage and reports real progress, but no LLM is called and no video is "
            "rendered. Tell the user this explicitly — do not describe the result "
            "as a finished video."
        )

    summary = (
        f"the whole repository at {repo_root}"
        if decision.scope is None
        else f"{decision.scope} (under {repo_root})"
    )

    record = build_job_record(
        goal=goal,
        requested_scope=decision.scope,
        root=repo_root,
        scope_mode=decision.mode,
        scope_summary=summary,
        notes=notes,
    )
    await deps.store.create(record)

    # Fire and forget. Awaiting the pipeline here would block the host for
    # minutes and defeat the entire job store.
    deps.runner.start(record)

    logger.info(
        "started job for %s (root=%s via %s, scope mode=%s, goal=%s)",
        summary,
        repo_root,
        root_decision.mode,
        decision.mode,
        (goal or "<none>")[:60],
        extra={"job_id": record.job_id},
    )

    return ExplainCodebaseResult(
        job_id=record.job_id,
        status="queued",
        scope_mode=decision.mode,
        resolved_scope_summary=summary,
        total_stages=TOTAL_STAGES,
        poll_hint=POLL_HINT,
        notes=notes,
    )


def register(mcp: "FastMCP", deps: "ToolDeps") -> None:
    """Bind ``deps`` into the tool callable and register it with the server."""
    from fastmcp.tools import Tool

    async def tool(
        goal: str | None = None,
        scope: str | None = None,
        root: str | None = None,
        ctx: "Context | None" = None,
    ) -> ExplainCodebaseResult:
        return await explain_codebase(deps, goal=goal, scope=scope, root=root, ctx=ctx)

    tool.__doc__ = explain_codebase.__doc__
    mcp.add_tool(
        Tool.from_function(tool, name=TOOL_NAME, description=TOOL_DESCRIPTION)
    )
