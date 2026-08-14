"""Turning a storyboard into slot files inside the job's Remotion project.

Two paths, and the order matters:

1. Deterministic: the storyboard is serialised straight into
   ``src/generated/storyboard.json`` and consumed by the scaffold's typed
   components. Most scenes need nothing more, and this path cannot produce a
   syntax error.
2. Generative: for anything the fixed components cannot express, the model
   writes ``src/generated/scenes.tsx`` against the documented component API.

Preferring (1) and falling back to (2) keeps the surface exposed to LLM error as
small as possible, which is also what makes the capped repair loop tractable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from code_explain_video_mcp.remotion.manifest import ScaffoldManifest
from code_explain_video_mcp.storyboard.schema import Storyboard

if TYPE_CHECKING:
    from code_explain_video_mcp.config import LLMSettings
    from code_explain_video_mcp.llm.client import LLMClient


@dataclass(slots=True)
class GeneratedCode:
    """The model's (or serialiser's) output, before it touches disk."""

    files: dict[str, str] = field(default_factory=dict)
    """Slot ``relative_path`` -> file contents."""

    composition_id: str = ""
    duration_in_frames: int = 0
    fps: int = 30
    width: int = 1920
    height: int = 1080
    generated_by: str = "deterministic"
    """``deterministic`` or ``llm``; recorded so failures can be attributed."""


def serialize_storyboard_props(storyboard: Storyboard) -> str:
    """Render the storyboard as the JSON props file the scaffold reads.

    The deterministic path — no model involved, so no syntax errors possible.
    """
    raise NotImplementedError


async def generate_scene_code(
    storyboard: Storyboard,
    manifest: ScaffoldManifest,
    client: "LLMClient",
    settings: "LLMSettings",
) -> GeneratedCode:
    """Ask the model to fill the scaffold's slots for this storyboard.

    Raises:
        CodeGenerationError: Output is missing slots, missing required exports,
            or tries to write outside the declared slots.
    """
    raise NotImplementedError


def extract_slot_files(raw_output: str, manifest: ScaffoldManifest) -> dict[str, str]:
    """Parse fenced/tagged model output into ``{relative_path: contents}``."""
    raise NotImplementedError


def write_generated_code(code: GeneratedCode, project_root: Path) -> list[Path]:
    """Write slot files into the job's project and return the paths written.

    Raises:
        CodeGenerationError: A target path escapes ``project_root`` or is not a
            declared slot.
    """
    raise NotImplementedError


def apply_fix(code: GeneratedCode, patched_files: dict[str, str]) -> GeneratedCode:
    """Overlay the repair pass's files onto the previous generation."""
    raise NotImplementedError
