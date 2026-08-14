"""Prompt construction for the three generative stages.

Prompts live here, apart from the nodes, for two reasons: they are the part most
likely to be iterated on, and they are worth testing directly (assert that the
goal appears, that the scaffold's slot list is enumerated, that error text is
included in the repair prompt).

The codegen prompt is the load-bearing one. Reliability comes from the scaffold:
the model is shown the existing components and their prop types and asked to
fill named slots, never to emit a Remotion project from scratch.
"""

from __future__ import annotations

from code_explain_video_mcp.context.chunking import ContextChunk
from code_explain_video_mcp.context.scope import ResolvedScope
from code_explain_video_mcp.remotion.manifest import ScaffoldManifest
from code_explain_video_mcp.remotion.validate import ValidationIssue
from code_explain_video_mcp.storyboard.schema import Storyboard

STORYBOARD_SYSTEM_PROMPT: str = (
    "You plan short code-explainer videos. You are given real source code and a "
    "viewer goal. Every scene must earn its screen time against that goal, and "
    "every code snippet must quote the provided source verbatim with correct "
    "line numbers. Never invent code that was not given to you."
)

CODEGEN_SYSTEM_PROMPT: str = (
    "You fill slots in an existing Remotion (React + TypeScript) project. The "
    "components, their props, and the composition shell already exist and must "
    "not be rewritten. Emit only the contents of the named slot files."
)

FIX_SYSTEM_PROMPT: str = (
    "You repair TypeScript compile and lint errors in generated Remotion scene "
    "code. Make the smallest change that clears the reported errors. Do not "
    "restructure working code and do not change the scaffold's component APIs."
)


def build_storyboard_prompt(
    scope: ResolvedScope,
    goal: str | None,
    chunks: list[ContextChunk],
    *,
    target_duration_seconds: float,
) -> str:
    """Assemble the stage-3 prompt: goal, scope summary, and numbered chunks.

    Chunks are rendered with their absolute line numbers so the model can cite
    ranges that ``check_snippet_references`` will accept.
    """
    raise NotImplementedError


def build_codegen_prompt(storyboard: Storyboard, manifest: ScaffoldManifest) -> str:
    """Assemble the stage-4 prompt: storyboard JSON plus the scaffold's slot contract."""
    raise NotImplementedError


def build_fix_prompt(
    generated_files: dict[str, str],
    issues: list[ValidationIssue],
    attempt: int,
    max_attempts: int,
) -> str:
    """Assemble the repair prompt for stage 6.

    ``attempt``/``max_attempts`` are included deliberately: on the final attempt
    the prompt instructs the model to prefer removing the offending scene over
    an ambitious fix, so the job degrades to a shorter video instead of failing.
    """
    raise NotImplementedError
