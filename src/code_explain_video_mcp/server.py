"""FastMCP application: the only module that knows about the MCP transport.

``create_server`` is a *factory*, not a module-level instance. FastMCP's
``fastmcp.json`` accepts either a server object or a factory as its
``entrypoint``, and the factory form is what lets settings, the job store, and
the compiled graph be constructed once at startup and injected, instead of
being reached for as globals from inside tool bodies.

The MCP surface is deliberately three tools wide:

* ``explain_codebase``   -- start a job, return a ``job_id`` immediately
* ``get_render_status``  -- poll a job
* ``get_storyboard``     -- read the storyboard as soon as stage 3 finishes

Pipeline stages (scope resolution, grepping, codegen, tsc, render) are NOT
tools. They are LangGraph nodes. If a new capability seems to need a fourth
tool, it almost certainly belongs in the graph instead.

Composition note: FastMCP supports ``mount()`` for combining sub-servers, which
is the right tool when a project has many tool families. With exactly three
tools there is nothing to namespace, so this server registers them directly via
``tools.register_tools`` and keeps a flat surface. If auth/admin tooling is ever
added, it should become a mounted sub-server rather than more top-level tools.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Final

from code_explain_video_mcp.logging_conf import configure_logging, get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from code_explain_video_mcp.config import Settings

logger = get_logger("server")

SERVER_NAME: Final[str] = "code-explain-video-mcp"

SERVER_INSTRUCTIONS: Final[str] = (
    "Generates a short explainer video for a codebase scope tied to a stated goal. "
    "Call explain_codebase to start a job; it returns a job_id immediately. "
    "Poll get_render_status with that job_id for progress and the final video path "
    "or URL. Call get_storyboard for the scene plan as soon as it is available, "
    "before the render finishes."
)


def create_server(settings: "Settings | None" = None) -> "FastMCP":
    """Build a fully wired FastMCP server.

    Responsibilities, in order:

    1. Resolve ``settings`` (falling back to ``config.load_settings()``).
    2. Configure stdio-safe logging.
    3. Construct the job store, workspace manager, and background runner.
    4. Compile the LangGraph pipeline once and hand it to the runner.
    5. Register the three tools against the resulting dependency bundle.
    6. Attach a lifespan that starts the optional static file server and
       cancels in-flight jobs plus reaps workspaces on shutdown.
    """
    from fastmcp import FastMCP

    from code_explain_video_mcp.config import load_settings
    from code_explain_video_mcp.graph import PipelineDeps, compile_pipeline, recursion_limit_for
    from code_explain_video_mcp.jobs import InMemoryJobStore, JobRunner, WorkspaceManager
    from code_explain_video_mcp.tools import ToolDeps, register_tools

    resolved = settings or load_settings()

    # stdio_safe unconditionally: even under HTTP, writing logs to stdout gains
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

    pipeline_deps = PipelineDeps(settings=resolved, store=store, workspaces=workspaces)
    pipeline = compile_pipeline(pipeline_deps)

    runner = JobRunner(
        settings=resolved,
        store=store,
        workspaces=workspaces,
        pipeline=pipeline,
        recursion_limit=recursion_limit_for(pipeline_deps),
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app: "FastMCP") -> AsyncIterator[None]:
        """Reap stale workspaces on the way in; cancel live jobs on the way out."""
        workspaces.reap(resolved.jobs.workspace_ttl_seconds, keep=runner.active_job_ids)
        logger.info(
            "%s ready — %d tools, dry_run=%s, workspaces at %s",
            SERVER_NAME,
            3,
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
        version="0.1.0",
        lifespan=lifespan,
    )
    register_tools(mcp, ToolDeps(settings=resolved, store=store, runner=runner))
    return mcp


def run(settings: "Settings | None" = None) -> None:
    """Create the server and block, serving on the configured transport.

    Note the spike's bug that this replaces: ``host``/``port`` are ignored
    unless ``transport="http"`` is passed explicitly, and ``host`` is a bind
    address (``127.0.0.1``), not a URL.

    ``run()`` defaults to stdio and swallows ``host``/``port`` into
    ``**transport_kwargs`` without raising, so a server that *looks* configured
    for HTTP will sit silently on stdio while clients fail to connect. The fix
    is to branch on the transport and only pass the network arguments when they
    mean something.
    """
    from code_explain_video_mcp.config import load_settings

    resolved = settings or load_settings()
    mcp = create_server(resolved)

    if resolved.transport == "stdio":
        # No banner: it would go to stdout and corrupt the protocol stream.
        mcp.run(transport="stdio", show_banner=False)
    else:
        logger.info(
            "serving over %s at http://%s:%d/mcp",
            resolved.transport,
            resolved.host,
            resolved.port,
        )
        mcp.run(
            transport=resolved.transport,
            show_banner=False,
            host=resolved.host,
            port=resolved.port,
        )
