"""The storyboard: the pipeline's central data contract.

Stage 3 produces a ``Storyboard``; stage 4 consumes it programmatically to fill
slots in the Remotion scaffold. Because a machine reads it, it is JSON with a
fixed schema — Markdown is generated *from* it for human review, never parsed back.

Any change to ``schema.py`` is a breaking change for ``generate_remotion_code``
and for the scaffold's TypeScript prop types, which are kept in sync by hand
(see ``remotion/scaffold/src/types.ts``).
"""

from __future__ import annotations

from code_explain_video_mcp.storyboard.markdown import render_markdown
from code_explain_video_mcp.storyboard.schema import (
    STORYBOARD_SCHEMA_VERSION,
    CodeSnippet,
    Scene,
    Storyboard,
)
from code_explain_video_mcp.storyboard.validation import (
    check_snippet_references,
    parse_storyboard,
)

__all__ = [
    "STORYBOARD_SCHEMA_VERSION",
    "CodeSnippet",
    "Scene",
    "Storyboard",
    "check_snippet_references",
    "parse_storyboard",
    "render_markdown",
]
