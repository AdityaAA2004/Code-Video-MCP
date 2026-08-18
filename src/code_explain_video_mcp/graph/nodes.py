"""One function per pipeline stage.

Nodes orchestrate; they do not contain business logic. Every stage does the
same four things, and :func:`_stage` is the single place they live:

1. push the stage into the job store so ``get_render_status`` can see it,
2. refuse to run for real while the stage's implementation is still missing,
3. call the stage body for the actual work,
4. log what it did and return a *partial* state update for LangGraph to merge.

Step 2 is the honesty guard. Only ``resolve_scope`` is implemented; every other
body fabricates a clearly-labelled placeholder so the whole async job lifecycle
can be exercised before a single LLM or Remotion integration exists. A stage
that declares ``needs=`` raises ``NotImplementedError`` unless
``Settings.dry_run`` is on, so a fake result can never be mistaken for a real
one. Drop the ``needs=`` argument as each stage lands.

The seven stages are assembled from their bodies in one table near the bottom.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from code_explain_video_mcp.context.scope import resolve_scope
from code_explain_video_mcp.graph.state import PipelineState
from code_explain_video_mcp.jobs.models import JobStage
from code_explain_video_mcp.logging_conf import get_logger
from code_explain_video_mcp.storyboard.schema import Scene, Storyboard

if TYPE_CHECKING:
    from code_explain_video_mcp.graph.deps import PipelineDeps

logger = get_logger("graph.nodes")

Node = Callable[[PipelineState], Awaitable[dict[str, object]]]
NodeFactory = Callable[["PipelineDeps"], Node]

StageResult = tuple[str, dict[str, object]]
"""What a stage body returns: a one-line detail, and a partial state update.

The detail is what shows up in the job log and in ``stage_log``; the update is
merged into the graph state by LangGraph.
"""

StageBody = Callable[["PipelineDeps", PipelineState], Awaitable[StageResult]]

DRY_RUN_STAGE_SECONDS: float = 1.5
"""How long each placeholder stage pretends to take.

Non-zero on purpose: a pipeline that completes instantly does not prove the
polling contract works. This is long enough that a host calling
``get_render_status`` actually observes intermediate stages.
"""

DRY_RUN_NOTE = (
    "DRY RUN: this job ran with placeholder pipeline stages. No LLM was called, "
    "no TypeScript was type-checked, and no video was rendered. The storyboard "
    "below is illustrative scaffolding, not an analysis of your code."
)


def _stage(name: JobStage, body: StageBody, *, needs: str | None = None) -> NodeFactory:
    """Bind one stage body into the node factory the graph registers.

    ``needs`` names the module that has to land before this body stops being a
    placeholder. While it is set, the stage refuses to run outside dry-run mode.
    """

    def make_node(deps: "PipelineDeps") -> Node:
        async def node(state: PipelineState) -> dict[str, object]:
            job_id = state["job_id"]
            await deps.store.enter_stage(job_id, name)
            logger.info("%s | start", name, extra={"job_id": job_id})

            if needs is not None:
                if not deps.settings.dry_run:
                    raise NotImplementedError(
                        f"{name} is not implemented; run with dry_run=True until "
                        f"{needs} lands."
                    )
                await asyncio.sleep(DRY_RUN_STAGE_SECONDS)

            detail, update = await body(deps, state)
            logger.info("%s | %s", name, detail, extra={"job_id": job_id})
            return {"stage": name, "stage_log": [f"{name}: {detail}"], **update}

        return node

    return make_node


# --------------------------------------------------------------------------
# Stage bodies
# --------------------------------------------------------------------------


async def _resolve_scope(deps: "PipelineDeps", state: PipelineState) -> StageResult:
    """Decide *what* is being explained, bounded by the configured caps.

    Real even in dry-run mode. It touches no LLM and no external binary, and
    "which files did it pick?" is the first thing worth checking when the
    plumbing is new — a placeholder here would hide the answer.
    """
    resolved = await asyncio.to_thread(
        resolve_scope,
        Path(state["root"]),
        state.get("requested_scope"),
        deps.settings.scope,
    )
    logger.debug(
        "resolve_scope | top files: %s",
        ", ".join(selected.relative_path for selected in resolved.files[:10]),
        extra={"job_id": state["job_id"]},
    )
    await deps.store.update(state["job_id"], scope_summary=resolved.summary)
    return resolved.summary, {"scope": resolved, "notes": list(resolved.notes)}


async def _gather_context(deps: "PipelineDeps", state: PipelineState) -> StageResult:
    """Read the parts of the selected files worth putting on screen.

    Placeholder: one chunk per selected file, carrying only what the storyboard
    stage needs to address a file by name and line range.
    """
    scope = state.get("scope")
    chunks = [
        {
            "relative_path": selected.relative_path,
            "language": selected.language,
            "kind": "file",
            "start_line": 1,
            "end_line": 1,
            "est_tokens": max(1, selected.size_bytes // 4),
            "placeholder": True,
        }
        for selected in (scope.files[:12] if scope is not None else [])
    ]
    return f"{len(chunks)} placeholder chunks", {"context_chunks": chunks}


async def _build_storyboard(deps: "PipelineDeps", state: PipelineState) -> StageResult:
    """Plan the scenes. The first of the three LLM stages."""
    storyboard = _placeholder_storyboard(state)
    # Publish immediately: get_storyboard is deliberately readable long before
    # the render finishes, and this is the moment it becomes valid.
    await deps.store.update(state["job_id"], storyboard=storyboard)
    return (
        f"{len(storyboard.scenes)} placeholder scenes, "
        f"{storyboard.total_duration_seconds:.1f}s runtime",
        {"storyboard": storyboard, "notes": [DRY_RUN_NOTE]},
    )


async def _generate_remotion_code(deps: "PipelineDeps", state: PipelineState) -> StageResult:
    """Fill slots in the checked-in Remotion scaffold from the storyboard."""
    storyboard = state.get("storyboard")
    scene_count = len(storyboard.scenes) if storyboard is not None else 0
    # The storyboard stops being editable the moment codegen reads it.
    await deps.store.update(state["job_id"], storyboard_consumed=True)
    generated = {
        "placeholder": True,
        "scene_count": scene_count,
        "total_frames": storyboard.total_frames if storyboard is not None else 0,
        "files": ["src/Composition.tsx", "src/scenes.generated.tsx"],
    }
    detail = f"{scene_count} scene slots in {deps.settings.render.scaffold_dir}"
    return detail, {"remotion_code": generated}


async def _validate_syntax(deps: "PipelineDeps", state: PipelineState) -> StageResult:
    """Type-check the generated project before spending minutes on a render.

    The dry run always reports a clean compile, so the happy path is what gets
    exercised. The fix_errors branch is still wired, and is covered by tests
    that inject errors directly into the state.
    """
    attempt = int(state.get("retry_count", 0)) + 1
    return f"0 errors (attempt {attempt})", {"validation_errors": []}


async def _fix_errors(deps: "PipelineDeps", state: PipelineState) -> StageResult:
    """Feed diagnostics back to the model. Capped by the router; never loops forever."""
    retry = int(state.get("retry_count", 0)) + 1
    await deps.store.update(state["job_id"], retry_count=retry)
    detail = f"retry {retry}/{deps.settings.render.max_fix_retries}"
    return detail, {"retry_count": retry, "validation_errors": []}


async def _render_video(deps: "PipelineDeps", state: PipelineState) -> StageResult:
    """Shell out to the Remotion CLI and publish the artifact."""
    storyboard = state.get("storyboard")
    frames = storyboard.total_frames if storyboard is not None else 0
    duration = storyboard.total_duration_seconds if storyboard is not None else 0.0

    # No MP4 is produced. Write a placeholder marker instead of an empty .mp4,
    # so nothing downstream can mistake this for a playable file.
    workspace = state.get("workspace")
    marker: Path | None = None
    if workspace is not None:
        marker = workspace.output_dir / "DRY_RUN_NO_VIDEO.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            "This job ran with dry_run=True. No video was rendered.\n"
            f"A real run would have written {workspace.video_path}\n"
            f"({frames} frames).\n",
            encoding="utf-8",
        )

    await deps.store.update(
        state["job_id"],
        video_path=marker,
        video_duration_seconds=duration,
        video_size_bytes=marker.stat().st_size if marker else None,
    )
    return f"DRY RUN, {frames} frames not rendered", {"status": "succeeded"}


def _placeholder_storyboard(state: PipelineState) -> Storyboard:
    """Build a schema-valid storyboard without calling a model.

    Schema-valid is the point: it proves ``get_storyboard`` returns something the
    host can actually deserialise, and it gives ``generate_remotion_code`` a real
    object shape to consume once it exists. The prose is honest about being
    placeholder text rather than pretending to describe the code.
    """
    scope = state.get("scope")
    goal = state.get("goal")
    scope_summary = scope.summary if scope is not None else "unknown scope"
    files = list(scope.files[:3]) if scope is not None else []

    scenes = [
        Scene(
            id="intro",
            kind="intro",
            title="What we're looking at",
            bullets=[
                f"Scope: {scope_summary}",
                f"Goal: {goal or 'not specified'}",
                "Placeholder scene — generated without an LLM",
            ],
            narration=(
                "This is a dry-run storyboard. The pipeline ran end to end, but the "
                "scene-planning stage returned scaffolding instead of an analysis."
            ),
            goal_tie_in=(
                "Once build_storyboard is implemented, this scene will frame the "
                f"codebase around: {goal or 'the stated goal'}"
            ),
            duration_seconds=6.0,
        )
    ]
    scenes += [
        Scene(
            id=f"file-{index}",
            title=selected.relative_path,
            bullets=[
                f"Ranked #{index} of the files in scope",
                f"{selected.size_bytes // 1024} KiB · {selected.language or 'unknown'}",
            ],
            narration=(
                f"A real run would explain what {selected.relative_path} does and why "
                "it ranked highly. This is placeholder narration."
            ),
            goal_tie_in="Placeholder tie-in; the real one is written by the storyboard model.",
            duration_seconds=8.0,
            transition_in="slide",
        )
        for index, selected in enumerate(files, start=1)
    ]
    scenes.append(
        Scene(
            id="outro",
            kind="outro",
            title="Dry run complete",
            bullets=[
                "All seven stages executed",
                "No LLM call, no tsc, no render",
                "Set dry_run=false as each stage lands",
            ],
            narration="The job lifecycle works. The stage bodies are next.",
            goal_tie_in="Confirms the plumbing that the real pipeline will run on.",
            duration_seconds=5.0,
        )
    )

    return Storyboard(
        title=f"[DRY RUN] Explainer for {scope_summary}",
        goal=goal,
        scope_summary=scope_summary,
        scenes=scenes,
    )


# --------------------------------------------------------------------------
# The seven stages
# --------------------------------------------------------------------------
# ``needs`` names the module a stage is still waiting on; while it is set, the
# stage runs only under dry_run. resolve_scope is the only one implemented.

make_resolve_scope = _stage("resolve_scope", _resolve_scope)
make_gather_context = _stage(
    "gather_context", _gather_context, needs="context.chunking"
)
make_build_storyboard = _stage(
    "build_storyboard", _build_storyboard, needs="llm.client"
)
make_generate_remotion_code = _stage(
    "generate_remotion_code", _generate_remotion_code, needs="remotion.codegen"
)
make_validate_syntax = _stage(
    "validate_syntax", _validate_syntax, needs="remotion.validate"
)
make_fix_errors = _stage("fix_errors", _fix_errors, needs="llm.client")
make_render_video = _stage("render_video", _render_video, needs="remotion.render")


# --------------------------------------------------------------------------
# The validate_syntax branch
# --------------------------------------------------------------------------


def make_should_fix(deps: "PipelineDeps") -> Callable[[PipelineState], str]:
    """Router for the ``validate_syntax`` → ``fix_errors`` / ``render_video`` branch.

    Three outcomes, and the third is the one that matters: exhausting the retry
    cap must fail the job with a clear message rather than looping. Returning a
    branch name (not raising) keeps that decision visible in the graph topology.
    """

    def should_fix(state: PipelineState) -> str:
        errors = state.get("validation_errors") or []
        retry = int(state.get("retry_count", 0))
        cap = deps.settings.render.max_fix_retries

        if not errors:
            branch = "render"
        elif retry >= cap:
            branch = "give_up"
        else:
            branch = "fix"

        logger.info(
            "router | %d error(s), retry %d/%d -> %s",
            len(errors),
            retry,
            cap,
            branch,
            extra={"job_id": state.get("job_id", "?")},
        )
        return branch

    return should_fix


def make_give_up(deps: "PipelineDeps") -> Node:
    """Terminal node for a validation loop that hit its cap."""

    async def give_up_node(state: PipelineState) -> dict[str, object]:
        errors = list(state.get("validation_errors") or [])
        cap = deps.settings.render.max_fix_retries
        message = (
            f"Generated Remotion code still failed type-checking after {cap} repair "
            f"attempt(s). First error: {errors[0] if errors else 'unknown'}"
        )
        logger.error("give_up | %s", message, extra={"job_id": state["job_id"]})
        return {
            "error": message,
            "status": "failed",
            "stage": "validate_syntax",
            "stage_log": [f"give_up: {len(errors)} unresolved error(s)"],
        }

    return give_up_node
