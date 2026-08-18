"""One-way rendering of a ``Storyboard`` into Markdown for human review.

``get_storyboard`` returns this alongside the JSON so a person can read the plan
without parsing structured output. The direction is strictly JSON -> Markdown;
nothing in the pipeline ever parses Markdown back into a storyboard.
"""

from __future__ import annotations

from code_explain_video_mcp.storyboard.schema import Scene, Storyboard


def render_markdown(storyboard: Storyboard) -> str:
    """Render the full storyboard as Markdown (title, then one section per scene)."""
    lines: list[str] = [f"# {storyboard.title}", ""]

    if storyboard.goal:
        lines += [f"**Goal:** {storyboard.goal}", ""]
    lines += [
        f"**Scope:** {storyboard.scope_summary}",
        "",
        render_summary_line(storyboard),
        "",
        "---",
        "",
    ]

    for index, scene in enumerate(storyboard.scenes, start=1):
        lines += [render_scene(scene, index), ""]

    return "\n".join(lines).rstrip() + "\n"


def render_scene(scene: Scene, index: int) -> str:
    """Render a single scene: heading, timing, bullets, snippet, goal tie-in."""
    lines: list[str] = [
        f"## {index}. {scene.title}",
        "",
        f"`{scene.kind}` · {scene.duration_seconds:g}s · transition: {scene.transition_in}",
        "",
    ]

    if scene.bullets:
        lines += [f"- {bullet}" for bullet in scene.bullets]
        lines.append("")

    snippet = scene.snippet
    if snippet is not None:
        lines += [
            f"**{snippet.path}** (lines {snippet.start_line}–{snippet.end_line})",
            "",
            f"```{snippet.language}",
            snippet.code.rstrip("\n"),
            "```",
            "",
        ]
        if snippet.highlight_lines:
            lines += [
                f"Highlighted: lines {', '.join(str(n) for n in snippet.highlight_lines)}",
                "",
            ]
        if snippet.caption:
            lines += [f"_{snippet.caption}_", ""]

    lines += [f"**Narration:** {scene.narration}", "", f"**Ties to goal:** {scene.goal_tie_in}"]
    return "\n".join(lines)


def render_summary_line(storyboard: Storyboard) -> str:
    """One-line digest (scene count, total runtime) for status responses."""
    minutes, seconds = divmod(round(storyboard.total_duration_seconds), 60)
    runtime = f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"
    return (
        f"{len(storyboard.scenes)} scenes · {runtime} · "
        f"{storyboard.width}×{storyboard.height} @ {storyboard.fps}fps "
        f"({storyboard.total_frames} frames)"
    )
