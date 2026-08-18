"""Code-explanation video MCP server.

Takes a codebase scope (file, folder, or whole repo) plus a user-stated goal and
produces a short Remotion-rendered explainer video.

Layering, outermost to innermost — imports run one way down this list:

1. ``server``    -- the FastMCP application; the only place transport lives.
2. ``tools``     -- the three host-callable MCP tools. Thin adapters only.
3. ``jobs``      -- job store, background runner, per-job workspaces. The bridge
                    between a synchronous tool call and a long pipeline.
4. ``graph``     -- the LangGraph pipeline: shared state, one node per stage.
                    Nodes orchestrate; they hold no business logic.
5. ``context`` / ``storyboard`` / ``llm`` / ``remotion``
                 -- the business logic the nodes call. These know nothing about
                    MCP or LangGraph and are unit-testable on their own.

Nothing is re-exported here: import from the subpackage that owns it, so the
dependency direction above stays visible at every call site.
"""

__version__ = "0.1.0"
