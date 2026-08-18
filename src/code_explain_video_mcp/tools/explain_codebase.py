"""Tool 1 of 3: ``explain_codebase`` — start a job, return a handle immediately.

Resolve the root, decide the scope, create the job record and workspace, hand
the job to the background runner, return the ``job_id``. This function must
never await the pipeline: a render takes minutes, this call takes milliseconds.

FastMCP 4 ships a protocol-native task extension (``@mcp.tool(task=True)``), but
it is negotiated per connection and clients without it fall back to *synchronous*
execution — which would block the host for a whole render. Our own job store
plus a ``job_id`` handle works on every client, so that is what this uses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from code_explain_video_mcp.jobs.models import TOTAL_STAGES
from code_explain_video_mcp.jobs.store import build_job_record
from code_explain_video_mcp.logging_conf import get_logger
from code_explain_video_mcp.tools.elicitation import resolve_requested_scope, resolve_root
from code_explain_video_mcp.tools.schemas import ExplainCodebaseResult

if TYPE_CHECKING:
    from fastmcp import Context

    from code_explain_video_mcp.tools import ToolDeps

logger = get_logger("tools.explain_codebase")

POLL_HINT = (
    "Call get_render_status with this job_id to track progress. Poll every few "
    "seconds; call get_storyboard as soon as storyboard_available is true to "
    "show the user the scene plan without waiting for the render."
)

DRY_RUN_NOTE = (
    "This server is running in DRY RUN mode: the pipeline executes every stage "
    "and reports real progress, but no LLM is called and no video is rendered. "
    "Tell the user this explicitly — do not describe the result as a finished video."
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
        deps: Bound at registration; not part of the host-visible schema.
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

    scope_decision = await resolve_requested_scope(
        scope, ctx, allow_elicitation=deps.settings.allow_elicitation
    )

    notes = [*root_decision.notes, *scope_decision.notes]
    if deps.settings.dry_run:
        notes.append(DRY_RUN_NOTE)

    summary = (
        f"the whole repository at {repo_root}"
        if scope_decision.scope is None
        else f"{scope_decision.scope} (under {repo_root})"
    )

    record = build_job_record(
        goal=goal,
        requested_scope=scope_decision.scope,
        root=repo_root,
        scope_mode=scope_decision.mode,
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
        scope_decision.mode,
        (goal or "<none>")[:60],
        extra={"job_id": record.job_id},
    )

    return ExplainCodebaseResult(
        job_id=record.job_id,
        status="queued",
        scope_mode=scope_decision.mode,
        resolved_scope_summary=summary,
        total_stages=TOTAL_STAGES,
        poll_hint=POLL_HINT,
        notes=notes,
    )
