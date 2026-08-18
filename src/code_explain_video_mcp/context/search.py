"""Ripgrep wrapper.

``gather_context`` greps for relevant regions instead of dumping whole files,
which is what keeps large repos inside the token budget. Shelling out to ``rg``
is much faster than walking in Python and already respects ``.gitignore``.

Both functions below are placeholders. See ``graph.nodes.make_gather_context``
for the dry-run stand-in that runs until they land.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One matching line, with the surrounding context ``rg -C`` returned."""

    path: Path
    line_number: int
    line: str
    before: list[str]
    after: list[str]


async def ripgrep(
    pattern: str,
    paths: list[Path],
    *,
    context_lines: int = 3,
    max_hits: int = 200,
    case_insensitive: bool = False,
) -> list[SearchHit]:
    """Run ripgrep and parse its JSON output into hits.

    Must degrade rather than fail: when no ``rg`` binary is on PATH, fall back
    to an equivalent pure-Python scan so the server still works on a machine
    without it.
    """
    raise NotImplementedError


def build_goal_queries(goal: str | None) -> list[str]:
    """Derive search patterns from the user's goal.

    A goal like "how does auth work" becomes identifier-ish patterns to grep for;
    with no goal, returns patterns for structural anchors (entrypoints, exported
    symbols, class definitions).
    """
    raise NotImplementedError
