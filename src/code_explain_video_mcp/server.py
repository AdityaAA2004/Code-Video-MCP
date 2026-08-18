"""FastMCP application: the only module that knows about the MCP transport.

``create_server`` is a *factory*, not a module-level instance. ``fastmcp.json``
accepts either, and the factory form is what lets settings, the job store, and
the compiled graph be built once at startup and injected, rather than reached
for as globals from inside tool bodies.

The MCP surface is deliberately three tools wide:

* ``explain_codebase``   -- start a job, return a ``job_id`` immediately
* ``get_render_status``  -- poll a job
* ``get_storyboard``     -- read the storyboard as soon as stage 3 finishes

Pipeline stages (scope resolution, codegen, tsc, render) are NOT tools; they are
LangGraph nodes. A capability that seems to need a fourth tool almost certainly
belongs in the graph instead.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastmcp import FastMCP

from code_explain_video_mcp import __version__
from code_explain_video_mcp.config import Settings, load_settings
from code_explain_video_mcp.graph import PipelineDeps, compile_pipeline, recursion_limit_for
from code_explain_video_mcp.jobs import InMemoryJobStore, JobRunner, WorkspaceManager
from code_explain_video_mcp.logging_conf import configure_logging, get_logger
from code_explain_video_mcp.tools import ToolDeps, register_tools

logger = get_logger("server")

SERVER_NAME = "code-explain-video-mcp"

SERVER_INSTRUCTIONS = (
    "Generates a short explainer video for a codebase scope tied to a stated goal. "
    "Call explain_codebase to start a job; it returns a job_id immediately. "
    "Poll get_render_status with that job_id for progress and the final video path "
    "or URL. Call get_storyboard for the scene plan as soon as it is available, "
    "before the render finishes."
)


def create_server(settings: Settings | None = None) -> FastMCP:
    """Build a fully wired FastMCP server: job store, pipeline, and three tools."""
    resolved = settings or load_settings()

    # stdio_safe unconditionally: even under HTTP, logging to stdout gains
    # nothing, and getting it wrong under stdio corrupts the JSON-RPC framing.
    configure_logging("INFO", stdio_safe=True)

    if resolved.jobs.store_backend != "memory":
        raise NotImplementedError(
            f"Job store backend {resolved.jobs.store_backend!r} is not implemented; "
            "only 'memory' exists in v1."
        )

    store = InMemoryJobStore()
    workspaces = WorkspaceManager(resolved.render)
    workspaces.root.mkdir(parents=True, exist_ok=True)
    resolved.render.output_root.mkdir(parents=True, exist_ok=True)

    deps = PipelineDeps(settings=resolved, store=store, workspaces=workspaces)
    runner = JobRunner(
        settings=resolved,
        store=store,
        workspaces=workspaces,
        pipeline=compile_pipeline(deps),
        recursion_limit=recursion_limit_for(deps),
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastMCP) -> AsyncIterator[None]:
        """Reap stale workspaces on the way in; cancel live jobs on the way out."""
        workspaces.reap(resolved.jobs.workspace_ttl_seconds, keep=runner.active_job_ids)
        logger.info(
            "%s ready — dry_run=%s, workspaces at %s",
            SERVER_NAME,
            resolved.dry_run,
            workspaces.root,
        )
        try:
            yield
        finally:
            await runner.shutdown()
            await store.reap(resolved.jobs.workspace_ttl_seconds)
            logger.info("%s shut down", SERVER_NAME)

    mcp = FastMCP(
        name=SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
        version=__version__,
        lifespan=lifespan,
    )
    register_tools(mcp, ToolDeps(settings=resolved, store=store, runner=runner))
    return mcp


def run(settings: Settings | None = None) -> None:
    """Create the server and block, serving on the configured transport.

    The transport must be passed explicitly. ``mcp.run()`` defaults to stdio and
    swallows ``host``/``port`` into ``**transport_kwargs`` without raising, so a
    server that *looks* configured for HTTP would sit silently on stdio while
    clients fail to connect. ``host`` is a bind address (``127.0.0.1``), not a URL.
    """
    resolved = settings or load_settings()
    mcp = create_server(resolved)

    if resolved.transport == "stdio":
        # No banner: it would go to stdout and corrupt the protocol stream.
        mcp.run(transport="stdio", show_banner=False)
    else:
        logger.info(
            "serving over %s at http://%s:%d/mcp", resolved.transport, resolved.host, resolved.port
        )
        mcp.run(
            transport=resolved.transport,
            show_banner=False,
            host=resolved.host,
            port=resolved.port,
        )
