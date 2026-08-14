"""Code understanding: what to explain, and what to read about it.

This package backs pipeline stages 1 and 2 and is the reason "whole repo" does
not blow the context window. It contains no MCP and no LangGraph imports — it is
plain library code over a filesystem, unit-testable against the sample repos in
``tests/fixtures/sample_repos``.

* ``scope``     -- walk, prune noise, rank, and cap files.
* ``search``    -- ripgrep wrapper for finding relevant regions.
* ``chunking``  -- pull functions/classes rather than dumping whole files, and
                   enforce the token budget.
"""

from __future__ import annotations

from code_explain_video_mcp.context.chunking import ContextChunk, extract_chunks, fit_to_budget
from code_explain_video_mcp.context.scope import ResolvedScope, SelectedFile, resolve_scope
from code_explain_video_mcp.context.search import SearchHit, ripgrep

__all__ = [
    "ContextChunk",
    "ResolvedScope",
    "SearchHit",
    "SelectedFile",
    "extract_chunks",
    "fit_to_budget",
    "resolve_scope",
    "ripgrep",
]
