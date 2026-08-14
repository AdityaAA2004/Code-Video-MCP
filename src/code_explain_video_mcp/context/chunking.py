"""Extracting explainable units of code and fitting them to a token budget.

Whole-file dumps waste budget and produce worse storyboards, so context is
assembled from *chunks*: a function, a class, or a grep hit plus its enclosing
definition. Every chunk keeps its absolute line range, because those line
numbers flow all the way through to ``CodeSnippet.start_line`` and end up
on screen.

``fit_to_budget`` is the last line of defence for the context ceiling: even
after scope capping, the selected chunks must be trimmed to fit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from code_explain_video_mcp.context.scope import SelectedFile
from code_explain_video_mcp.context.search import SearchHit

ChunkKind = Literal["function", "class", "module_docstring", "region", "file"]


@dataclass(frozen=True, slots=True)
class ContextChunk:
    """A quotable region of one file, carried in the graph state."""

    relative_path: str
    language: str | None
    kind: ChunkKind
    symbol: str | None
    """Function/class name where applicable."""

    start_line: int
    """1-based inclusive."""

    end_line: int
    """1-based inclusive."""

    text: str
    est_tokens: int
    relevance: float = 0.0
    """Higher means more likely to be worth screen time."""

    reasons: list[str] = field(default_factory=list)
    """Why this chunk was selected — grep hit, entrypoint, high centrality."""


def extract_chunks(
    file: SelectedFile,
    *,
    hits: list[SearchHit] | None = None,
    max_chunk_lines: int = 120,
) -> list[ContextChunk]:
    """Split one file into chunks, biased toward regions containing ``hits``.

    Uses a real parser where one is available for the language and falls back to
    indentation/brace heuristics otherwise, so an unknown language still yields
    usable regions instead of nothing.
    """
    raise NotImplementedError


def extract_python_chunks(source: str, relative_path: str) -> list[ContextChunk]:
    """AST-based extraction for Python: module docstring, classes, functions."""
    raise NotImplementedError


def extract_heuristic_chunks(
    source: str, relative_path: str, language: str | None
) -> list[ContextChunk]:
    """Parser-free fallback: split on blank lines and brace/indent structure."""
    raise NotImplementedError


def estimate_tokens(text: str) -> int:
    """Cheap token estimate used for budgeting; deliberately approximate."""
    raise NotImplementedError


def fit_to_budget(chunks: list[ContextChunk], max_tokens: int) -> list[ContextChunk]:
    """Drop and/or truncate chunks by relevance until they fit ``max_tokens``.

    Raises:
        ContextBudgetExceededError: If even the single highest-relevance chunk
            cannot be trimmed under the ceiling.
    """
    raise NotImplementedError


def read_lines(path: Path, start_line: int, end_line: int) -> str:
    """Read an inclusive 1-based line range; the single place off-by-ones live."""
    raise NotImplementedError
