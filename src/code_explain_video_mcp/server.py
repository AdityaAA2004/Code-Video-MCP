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

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from code_explain_video_mcp.config import Settings

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
    raise NotImplementedError


def run(settings: "Settings | None" = None) -> None:
    """Create the server and block, serving on the configured transport.

    Note the spike's bug that this replaces: ``host``/``port`` are ignored
    unless ``transport="http"`` is passed explicitly, and ``host`` is a bind
    address (``127.0.0.1``), not a URL.
    """
    raise NotImplementedError
