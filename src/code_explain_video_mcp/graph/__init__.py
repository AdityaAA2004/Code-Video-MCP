"""The LangGraph pipeline.

Everything the architecture doc calls an internal stage lives here, and nothing
here is reachable as an MCP tool. The split is the load-bearing design decision
of the project: adding pipeline capability means adding a node, never a fourth
tool.

* ``state``    -- the one state object threaded through every node.
* ``deps``     -- server-scoped collaborators bound into nodes as closures.
* ``nodes``    -- one function per stage; orchestration only.
* ``pipeline`` -- topology and compilation.

This package imports LangGraph but not FastMCP, so the whole pipeline is
runnable from a plain script with no server process.
"""

from __future__ import annotations

from code_explain_video_mcp.graph.deps import PipelineDeps
from code_explain_video_mcp.graph.pipeline import (
    build_graph,
    compile_pipeline,
    recursion_limit_for,
)
from code_explain_video_mcp.graph.state import PipelineState, initial_state

__all__ = [
    "PipelineDeps",
    "PipelineState",
    "build_graph",
    "compile_pipeline",
    "initial_state",
    "recursion_limit_for",
]
