"""One-way rendering of a ``Storyboard`` into Markdown for human review.

``get_storyboard`` returns this alongside the JSON so a person can read the plan
without parsing structured output. The direction is strictly JSON -> Markdown;
nothing in the pipeline ever parses Markdown back into a storyboard.
"""

from __future__ import annotations

from code_explain_video_mcp.storyboard.schema import Scene, Storyboard


def render_markdown(storyboard: Storyboard, *, include_code: bool = True) -> str:
    """Render the full storyboard as Markdown (title, then one section per scene)."""
    raise NotImplementedError


def render_scene(scene: Scene, index: int, *, include_code: bool = True) -> str:
    """Render a single scene: heading, timing, bullets, snippet, goal tie-in."""
    raise NotImplementedError


def render_summary_line(storyboard: Storyboard) -> str:
    """One-line digest (scene count, total runtime) for status responses."""
    raise NotImplementedError
