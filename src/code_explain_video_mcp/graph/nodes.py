"""One function per pipeline stage.

Nodes orchestrate; they do not contain business logic. Each one does the same
four things and nothing else:

1. announce itself into the job log (this is the trace a user watches),
2. push the current stage into the job store so ``get_render_status`` can see it,
3. call into ``context`` / ``storyboard`` / ``llm`` / ``remotion`` for the actual
   work,
4. return a *partial* state update for LangGraph to merge.

Step 3 is the only part that differs between dry-run and real execution. Under
``Settings.dry_run`` the node substitutes a clearly-labelled placeholder for the
call it would make, which is what lets the entire async job lifecycle be
exercised before a single LLM or Remotion integration exists. Every placeholder
is marked ``DRY RUN`` in the log and in the user-facing notes, so a fake result
can never be mistaken for a real one.

Node bodies are factories (``make_<stage>(deps)``) returning the closure the
graph registers. See :mod:`code_explain_video_mcp.graph.deps` for why.
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
from code_explain_video_mcp.storyboard.schema import CodeSnippet, Scene, Storyboard

if TYPE_CHECKING:
    from code_explain_video_mcp.graph.deps import PipelineDeps

logger = get_logger("graph.nodes")

Node = Callable[[PipelineState], Awaitable[dict[str, object]]]

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


async def _announce(
    deps: "PipelineDeps", state: PipelineState, stage: JobStage, detail: str
) -> None:
    """Log the stage and mirror it into the job store in one place."""
    job_id = state["job_id"]
    logger.info("%s | %s", stage, detail, extra={"job_id": job_id})
    await deps.store.enter_stage(job_id, stage)


def _dry(deps: "PipelineDeps") -> bool:
    """Whether placeholder stage bodies are in effect."""
    return deps.settings.dry_run


# --------------------------------------------------------------------------
# Stage 1 — resolve_scope
# --------------------------------------------------------------------------


def make_resolve_scope(deps: "PipelineDeps") -> Node:
    """Decide *what* is being explained, bounded by the configured caps.

    This stage is real even in dry-run mode. It touches no LLM and no external
    binary, and "which files did it pick?" is the first thing worth checking
    when the plumbing is new — a placeholder here would hide the answer.
    """

    async def resolve_scope_node(state: PipelineState) -> dict[str, object]:
        await _announce(
            deps,
            state,
            "resolve_scope",
            f"root={state['root']} requested={state.get('requested_scope') or '<whole repo>'}",
        )

        resolved = await asyncio.to_thread(
            resolve_scope,
            Path(state["root"]),
            state.get("requested_scope"),
            deps.settings.scope,
        )

        logger.info(
            "resolve_scope | selected %d file(s), %d KiB%s",
            len(resolved.files),
            resolved.total_bytes // 1024,
            f", dropped {resolved.dropped_file_count}" if resolved.truncated else "",
            extra={"job_id": state["job_id"]},
        )
        for selected in resolved.files[:10]:
            logger.debug(
                "resolve_scope |   %-56s score=%.3f",
                selected.relative_path,
                selected.score,
                extra={"job_id": state["job_id"]},
            )

        await deps.store.update(state["job_id"], scope_summary=resolved.summary)
        return {
            "scope": resolved,
            "stage": "resolve_scope",
            "notes": list(resolved.notes),
            "stage_log": [f"resolve_scope: {resolved.summary}"],
        }

    return resolve_scope_node


# --------------------------------------------------------------------------
# Stage 2 — gather_context
# --------------------------------------------------------------------------


def make_gather_context(deps: "PipelineDeps") -> Node:
    """Read the parts of the selected files worth putting on screen."""

    async def gather_context_node(state: PipelineState) -> dict[str, object]:
        scope = state.get("scope")
        file_count = len(scope.files) if scope is not None else 0
        await _announce(deps, state, "gather_context", f"chunking {file_count} file(s)")

        if not _dry(deps):
            raise NotImplementedError(
                "gather_context: chunking/ripgrep integration is not implemented; "
                "run with dry_run=True until context.chunking lands."
            )

        await asyncio.sleep(DRY_RUN_STAGE_SECONDS)
        # Placeholder chunks: one per selected file, carrying only what the
        # storyboard stage needs to address a file by name and line range.
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
        logger.info(
            "gather_context | DRY RUN: fabricated %d placeholder chunk(s) "
            "instead of grepping and parsing",
            len(chunks),
            extra={"job_id": state["job_id"]},
        )
        return {
            "context_chunks": chunks,
            "stage": "gather_context",
            "stage_log": [f"gather_context: {len(chunks)} placeholder chunks"],
        }

    return gather_context_node


# --------------------------------------------------------------------------
# Stage 3 — build_storyboard
# --------------------------------------------------------------------------


def make_build_storyboard(deps: "PipelineDeps") -> Node:
    """Plan the scenes. The first of the three LLM stages."""

    async def build_storyboard_node(state: PipelineState) -> dict[str, object]:
        await _announce(
            deps,
            state,
            "build_storyboard",
            f"model={deps.settings.llm.storyboard_model} "
            f"chunks={len(state.get('context_chunks') or [])}",
        )

        if not _dry(deps):
            raise NotImplementedError(
                "build_storyboard: the LLM call is not implemented; run with "
                "dry_run=True until llm.client lands."
            )

        await asyncio.sleep(DRY_RUN_STAGE_SECONDS)
        storyboard = _placeholder_storyboard(state)

        # Publish immediately: get_storyboard is deliberately readable long
        # before the render finishes, and this is the moment it becomes valid.
        await deps.store.update(state["job_id"], storyboard=storyboard)
        logger.info(
            "build_storyboard | DRY RUN: %d placeholder scene(s), %.1fs runtime "
            "— storyboard is now readable via get_storyboard",
            len(storyboard.scenes),
            storyboard.total_duration_seconds,
            extra={"job_id": state["job_id"]},
        )
        return {
            "storyboard": storyboard,
            "stage": "build_storyboard",
            "notes": [DRY_RUN_NOTE],
            "stage_log": [f"build_storyboard: {len(storyboard.scenes)} scenes"],
        }

    return build_storyboard_node


def _placeholder_storyboard(state: PipelineState) -> Storyboard:
    """Build a schema-valid storyboard without calling a model.

    Schema-valid is the point: it proves ``get_storyboard`` returns something the
    host can actually deserialise, and it gives ``generate_remotion_code`` a real
    object shape to consume once it exists. The prose is honest about being
    placeholder text rather than pretending to describe the code.
    """
    scope = state.get("scope")
    goal = state.get("goal")
    files = list(scope.files[:3]) if scope is not None else []
    scope_summary = scope.summary if scope is not None else "unknown scope"

    scenes: list[Scene] = [
        Scene(
            id="intro",
            kind="intro",
            title="What we're looking at",
            bullets=[
                f"Scope: {scope_summary}",
                f"Goal: {goal}" if goal else "Goal: not specified",
                "Placeholder scene — generated without an LLM",
            ],
            narration=(
                "This is a dry-run storyboard. The pipeline ran end to end, but the "
                "scene-planning stage returned scaffolding instead of an analysis."
            ),
            goal_tie_in=(
                f"Once build_storyboard is implemented, this scene will frame the "
                f"codebase around: {goal}"
                if goal
                else "Once build_storyboard is implemented, this scene will frame the goal."
            ),
            duration_seconds=6.0,
            transition_in="fade",
        )
    ]

    for index, selected in enumerate(files, start=1):
        snippet = None
        first_line = _first_nonempty_line(selected.path)
        if first_line is not None:
            snippet = CodeSnippet(
                path=selected.relative_path,
                language=selected.language or "text",
                start_line=1,
                end_line=1,
                code=first_line,
                caption="Placeholder: line 1 only, not a chosen excerpt",
            )
        scenes.append(
            Scene(
                id=f"file-{index}",
                kind="walkthrough",
                title=selected.relative_path,
                bullets=[
                    f"Ranked #{index} by {'import centrality' if selected.score else 'size'}",
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
        )

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
            transition_in="fade",
        )
    )

    return Storyboard(
        title=f"[DRY RUN] Explainer for {scope_summary}",
        goal=goal,
        scope_summary=scope_summary,
        scenes=scenes,
    )


def _first_nonempty_line(path: Path) -> str | None:
    """Return a file's first non-blank line, or ``None`` if unreadable."""
    try:
        with Path(path).open(encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if line.strip():
                    return line.rstrip("\n")
    except OSError:
        return None
    return None


# --------------------------------------------------------------------------
# Stage 4 — generate_remotion_code
# --------------------------------------------------------------------------


def make_generate_remotion_code(deps: "PipelineDeps") -> Node:
    """Fill slots in the checked-in Remotion scaffold from the storyboard."""

    async def generate_remotion_code_node(state: PipelineState) -> dict[str, object]:
        storyboard = state.get("storyboard")
        scene_count = len(storyboard.scenes) if storyboard is not None else 0
        await _announce(
            deps,
            state,
            "generate_remotion_code",
            f"model={deps.settings.llm.codegen_model} scenes={scene_count}",
        )

        # The storyboard stops being editable the moment codegen reads it.
        await deps.store.update(state["job_id"], storyboard_consumed=True)

        if not _dry(deps):
            raise NotImplementedError(
                "generate_remotion_code: scaffold slot filling is not implemented; "
                "run with dry_run=True until remotion.codegen lands."
            )

        await asyncio.sleep(DRY_RUN_STAGE_SECONDS)
        generated = {
            "placeholder": True,
            "scene_count": scene_count,
            "total_frames": storyboard.total_frames if storyboard is not None else 0,
            "files": ["src/Composition.tsx", "src/scenes.generated.tsx"],
        }
        logger.info(
            "generate_remotion_code | DRY RUN: would fill %d scene slot(s) in the "
            "scaffold at %s (%d frames total)",
            scene_count,
            deps.settings.render.scaffold_dir,
            generated["total_frames"],
            extra={"job_id": state["job_id"]},
        )
        return {
            "remotion_code": generated,
            "stage": "generate_remotion_code",
            "stage_log": [f"generate_remotion_code: {scene_count} scene slots"],
        }

    return generate_remotion_code_node


# --------------------------------------------------------------------------
# Stage 5 — validate_syntax  (and the capped repair loop)
# --------------------------------------------------------------------------


def make_validate_syntax(deps: "PipelineDeps") -> Node:
    """Type-check the generated project before spending minutes on a render."""

    async def validate_syntax_node(state: PipelineState) -> dict[str, object]:
        retry = int(state.get("retry_count", 0))
        await _announce(
            deps,
            state,
            "validate_syntax",
            f"tsc --noEmit (attempt {retry + 1}/{deps.settings.render.max_fix_retries + 1})",
        )

        if not _dry(deps):
            raise NotImplementedError(
                "validate_syntax: the tsc/eslint integration is not implemented; "
                "run with dry_run=True until remotion.validate lands."
            )

        await asyncio.sleep(DRY_RUN_STAGE_SECONDS)
        # Dry run always reports a clean compile, so the happy path is what gets
        # exercised. The fix_errors branch is still wired and is covered by
        # tests that inject errors directly into the state.
        logger.info(
            "validate_syntax | DRY RUN: reporting 0 diagnostics (the repair loop "
            "is wired but not exercised on this path)",
            extra={"job_id": state["job_id"]},
        )
        return {
            "validation_errors": [],
            "stage": "validate_syntax",
            "stage_log": ["validate_syntax: 0 errors"],
        }

    return validate_syntax_node


def make_fix_errors(deps: "PipelineDeps") -> Node:
    """Feed diagnostics back to the model. Capped; never loops forever."""

    async def fix_errors_node(state: PipelineState) -> dict[str, object]:
        errors = list(state.get("validation_errors") or [])
        retry = int(state.get("retry_count", 0)) + 1
        await _announce(
            deps,
            state,
            "fix_errors",
            f"repairing {len(errors)} diagnostic(s), retry {retry}/"
            f"{deps.settings.render.max_fix_retries}",
        )
        await deps.store.update(state["job_id"], retry_count=retry)

        if not _dry(deps):
            raise NotImplementedError(
                "fix_errors: the repair LLM call is not implemented; run with "
                "dry_run=True until llm.client lands."
            )

        await asyncio.sleep(DRY_RUN_STAGE_SECONDS)
        logger.info(
            "fix_errors | DRY RUN: clearing diagnostics without a model call",
            extra={"job_id": state["job_id"]},
        )
        return {
            "retry_count": retry,
            "validation_errors": [],
            "stage": "fix_errors",
            "stage_log": [f"fix_errors: retry {retry}"],
        }

    return fix_errors_node


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
        job_id = state.get("job_id", "?")

        if not errors:
            logger.debug("router | clean compile -> render", extra={"job_id": job_id})
            return "render"
        if retry >= cap:
            logger.warning(
                "router | %d error(s) still present after %d/%d repair attempts -> give up",
                len(errors),
                retry,
                cap,
                extra={"job_id": job_id},
            )
            return "give_up"
        logger.info(
            "router | %d error(s), retry %d/%d -> fix",
            len(errors),
            retry,
            cap,
            extra={"job_id": job_id},
        )
        return "fix"

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


# --------------------------------------------------------------------------
# Stage 6 — render_video
# --------------------------------------------------------------------------


def make_render_video(deps: "PipelineDeps") -> Node:
    """Shell out to the Remotion CLI and publish the artifact."""

    async def render_video_node(state: PipelineState) -> dict[str, object]:
        storyboard = state.get("storyboard")
        frames = storyboard.total_frames if storyboard is not None else 0
        await _announce(
            deps,
            state,
            "render_video",
            f"composition={deps.settings.render.composition_id} frames={frames}",
        )

        if not _dry(deps):
            raise NotImplementedError(
                "render_video: the Remotion CLI integration is not implemented; "
                "run with dry_run=True until remotion.render lands."
            )

        await asyncio.sleep(DRY_RUN_STAGE_SECONDS)

        # No MP4 is produced. Write a placeholder marker instead of an empty
        # .mp4, so nothing downstream can mistake this for a playable file.
        workspace = state.get("workspace")
        marker: Path | None = None
        if workspace is not None:
            marker = workspace.output_dir / "DRY_RUN_NO_VIDEO.txt"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(
                "This job ran with dry_run=True. No video was rendered.\n"
                f"A real run would have written {workspace.video_path}\n"
                f"({frames} frames at {storyboard.fps if storyboard else 30} fps).\n",
                encoding="utf-8",
            )

        duration = storyboard.total_duration_seconds if storyboard is not None else 0.0
        await deps.store.update(
            state["job_id"],
            video_path=marker,
            video_duration_seconds=duration,
            video_size_bytes=marker.stat().st_size if marker else None,
        )
        logger.info(
            "render_video | DRY RUN: no MP4 produced; wrote marker at %s",
            marker,
            extra={"job_id": state["job_id"]},
        )
        return {
            "video_path": marker,
            "stage": "render_video",
            "status": "succeeded",
            "stage_log": [f"render_video: DRY RUN, {frames} frames not rendered"],
        }

    return render_video_node
