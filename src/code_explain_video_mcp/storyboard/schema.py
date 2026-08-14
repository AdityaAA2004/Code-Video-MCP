"""The fixed storyboard JSON schema.

Per the architecture doc, a storyboard is a list of scenes, each with a title,
bullet points, a code snippet with line references, narration text, an explicit
tie-in to the user's goal, and an estimated duration.

Two consumers depend on these exact field names:

* ``generate_remotion_code``, which maps scenes onto scaffold components.
* ``remotion/scaffold/src/types.ts``, the TypeScript mirror of these models.

The JSON Schema derived from these models is also what constrains the LLM call
in ``build_storyboard`` (structured output), so descriptions here double as
instructions to the model.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, Field

STORYBOARD_SCHEMA_VERSION: Final[str] = "1.0"

SceneKind = Literal["intro", "walkthrough", "diagram", "callout", "outro"]
TransitionKind = Literal["cut", "fade", "slide", "zoom"]


class CodeSnippet(BaseModel):
    """A quoted region of a real file, with the refs needed to prove it is real.

    ``start_line``/``end_line`` are 1-based and inclusive, and must correspond to
    the file at ``path`` — ``validation.check_snippet_references`` enforces this
    so the LLM cannot invent line numbers.
    """

    path: str = Field(description="Repo-relative path of the source file.")
    language: str = Field(description="Highlighter language id, e.g. 'python', 'tsx'.")
    start_line: int = Field(ge=1, description="1-based inclusive first line.")
    end_line: int = Field(ge=1, description="1-based inclusive last line.")
    code: str = Field(description="Verbatim source text for the line range.")
    highlight_lines: list[int] = Field(
        default_factory=list,
        description="Absolute line numbers to emphasise during this scene.",
    )
    caption: str | None = Field(
        default=None, description="One-line label shown under the snippet."
    )


class Scene(BaseModel):
    """One beat of the video."""

    id: str = Field(description="Stable slug, unique within the storyboard.")
    kind: SceneKind = Field(default="walkthrough")
    title: str = Field(description="On-screen heading.")
    bullets: list[str] = Field(
        default_factory=list, description="Short on-screen points, not full sentences."
    )
    snippet: CodeSnippet | None = Field(
        default=None, description="Code shown in this scene, if any."
    )
    narration: str = Field(description="Spoken/subtitle text; drives pacing.")
    goal_tie_in: str = Field(
        description="One sentence connecting this scene to the user's stated goal."
    )
    duration_seconds: float = Field(
        gt=0, description="Estimated on-screen duration; summed into total runtime."
    )
    transition_in: TransitionKind = Field(default="fade")


class Storyboard(BaseModel):
    """The complete plan for one video."""

    schema_version: str = Field(default=STORYBOARD_SCHEMA_VERSION)
    title: str
    goal: str | None = Field(
        default=None, description="The user's goal, verbatim, as given to explain_codebase."
    )
    scope_summary: str = Field(description="What was actually covered, in one line.")
    scenes: list[Scene] = Field(min_length=1)
    fps: int = Field(default=30, gt=0)
    width: int = Field(default=1920, gt=0)
    height: int = Field(default=1080, gt=0)

    @property
    def total_duration_seconds(self) -> float:
        """Sum of scene durations; the composition's length."""
        raise NotImplementedError

    @property
    def total_frames(self) -> int:
        """``total_duration_seconds * fps``, rounded for Remotion's durationInFrames."""
        raise NotImplementedError
