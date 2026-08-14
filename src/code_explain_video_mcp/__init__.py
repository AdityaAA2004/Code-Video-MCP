"""Code-explanation video MCP server.

An MCP server that takes a codebase scope (file, folder, or whole repo) plus a
user-stated goal and produces a short Remotion-rendered explainer video.

Layering (outermost to innermost):

1. ``server``    -- the FastMCP application; the only place transport lives.
2. ``tools``     -- the three host-callable MCP tools. Thin adapters only:
                    validate input, talk to the job store, format responses.
3. ``jobs``      -- async job store, background runner, per-job workspaces.
                    The bridge between a synchronous tool call and a long pipeline.
4. ``graph``     -- the LangGraph pipeline: shared state + one node per stage.
                    Nodes orchestrate; they do not contain business logic.
5. ``context`` / ``storyboard`` / ``llm`` / ``remotion`` / ``delivery``
                 -- the business logic the nodes call into. These packages know
                    nothing about MCP or LangGraph and are unit-testable alone.

Only ``server.create_server`` and the version are exported here. Everything else
should be imported from its own subpackage so the dependency direction above
stays obvious.
"""

from __future__ import annotations

from typing import Final

__version__: Final[str] = "0.1.0"

__all__ = ["__version__", "create_server"]


def __getattr__(name: str) -> object:
    """Lazily expose ``create_server`` without importing FastMCP at package import.

    Keeping this lazy means ``import code_explain_video_mcp`` stays cheap for
    tests that only touch the pure-logic subpackages.
    """
    if name == "create_server":
        from code_explain_video_mcp.server import create_server

        return create_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
