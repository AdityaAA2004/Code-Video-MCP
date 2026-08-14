"""The MCP surface: exactly three host-callable tools.

Each tool lives in its own module and exposes a plain ``async def`` plus a
``register(mcp, deps)`` function. Registration is functional
(``mcp.add_tool(...)``) rather than decorator-at-definition, because a decorator
would bind the tool to a module-level server instance and defeat the factory in
``server.create_server``.

Tool bodies stay thin: parse and validate arguments, call into ``jobs`` or the
graph, shape the response. No pipeline logic here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from code_explain_video_mcp.config import Settings
    from code_explain_video_mcp.jobs.runner import JobRunner
    from code_explain_video_mcp.jobs.store import JobStore

__all__ = ["ToolDeps", "register_tools"]


@dataclass(frozen=True, slots=True)
class ToolDeps:
    """Everything the three tools are allowed to touch.

    Passing this explicitly (instead of importing globals) is what makes the
    tools testable without a running server.
    """

    settings: "Settings"
    store: "JobStore"
    runner: "JobRunner"


def register_tools(mcp: "FastMCP", deps: ToolDeps) -> None:
    """Register ``explain_codebase``, ``get_render_status``, ``get_storyboard``.

    Adding a fourth registration here is a design change, not a feature: the
    architecture explicitly caps the host-visible surface at three.
    """
    raise NotImplementedError
