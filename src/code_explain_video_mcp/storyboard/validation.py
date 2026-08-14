"""Guarding the storyboard before it reaches codegen.

Schema conformance alone is not enough: a model can emit a perfectly typed
``CodeSnippet`` whose line numbers or code text do not match the real file. Since
the video's whole value is that it shows the user's actual code, snippet refs
are checked against disk here and mismatches are treated as a stage-3 failure
(retried at the LLM level) rather than being passed downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from code_explain_video_mcp.storyboard.schema import Storyboard


@dataclass(frozen=True, slots=True)
class SnippetIssue:
    """A single mismatch between a snippet and the file it claims to quote."""

    scene_id: str
    path: str
    reason: str


def parse_storyboard(raw: str | bytes | dict[str, object]) -> Storyboard:
    """Parse and schema-validate raw model output into a ``Storyboard``.

    Raises:
        StoryboardValidationError: With a message shaped for feeding back to the
            model on retry, not a raw pydantic traceback.
    """
    raise NotImplementedError


def check_snippet_references(storyboard: Storyboard, repo_root: Path) -> list[SnippetIssue]:
    """Verify every snippet's path, line range, and text against the real file.

    Returns an empty list when the storyboard is trustworthy.
    """
    raise NotImplementedError


def assert_durations_sane(storyboard: Storyboard, max_total_seconds: float) -> None:
    """Reject storyboards whose total runtime blows the video-length budget.

    Raises:
        StoryboardValidationError: If the summed duration exceeds the cap.
    """
    raise NotImplementedError
