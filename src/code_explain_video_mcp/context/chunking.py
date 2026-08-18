"""Extracting explainable units of code and fitting them to a token budget.

Whole-file dumps waste budget and produce worse storyboards, so context is
assembled from *chunks*: a function, a class, or a grep hit plus its enclosing
definition. Every chunk keeps its absolute line range, because those line
numbers flow all the way through to ``CodeSnippet.start_line`` and end up on
screen — this module is where off-by-one errors would become visible bugs.

``fit_to_budget`` is the last line of defence for the context ceiling: even
after scope capping, the selected chunks must be trimmed to fit.

Both functions below are placeholders. See ``graph.nodes.make_gather_context``
for the dry-run stand-in that runs until they land.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from code_explain_video_mcp.context.scope import SelectedFile
from code_explain_video_mcp.context.search import SearchHit

ChunkKind = Literal["function", "class", "module_docstring", "region", "file"]


@dataclass(frozen=True, slots=True)
class ContextChunk:
    """A quotable region of one file, carried in the graph state.

    ``start_line``/``end_line`` are 1-based and inclusive. ``symbol`` is the
    function or class name where one applies. ``reasons`` records why the chunk
    was selected (grep hit, entrypoint, high centrality) so a storyboard can
    justify the screen time.
    """

    relative_path: str
    language: str | None
    kind: ChunkKind
    symbol: str | None
    start_line: int
    end_line: int
    text: str
    est_tokens: int
    relevance: float = 0.0
    """Higher means more likely to be worth screen time."""

    reasons: list[str] = field(default_factory=list)


def extract_chunks(
    file: SelectedFile,
    *,
    hits: list[SearchHit] | None = None,
    max_chunk_lines: int = 120,
) -> list[ContextChunk]:
    """Split one file into chunks, biased toward regions containing ``hits``.

    Should use a real parser where one exists for the language (``ast`` for
    Python) and fall back to indentation/brace heuristics otherwise, so an
    unknown language still yields usable regions instead of nothing.
    """
    raise NotImplementedError


def fit_to_budget(chunks: list[ContextChunk], max_tokens: int) -> list[ContextChunk]:
    """Drop and/or truncate chunks by relevance until they fit ``max_tokens``.

    Raises:
        ContextBudgetExceededError: If even the single highest-relevance chunk
            cannot be trimmed under the ceiling.
    """
    raise NotImplementedError
