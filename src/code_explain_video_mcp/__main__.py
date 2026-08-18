"""Console entrypoint: ``python -m code_explain_video_mcp`` / the installed script.

This exists alongside ``fastmcp.json`` on purpose. ``fastmcp run`` is the
preferred path — it owns the environment and transport declaratively — but hosts
that only know how to spawn a command need a plain executable, and that is what
this module provides. Neither path holds logic: both converge on
``server.run(load_settings(...))``.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from code_explain_video_mcp.config import load_settings
from code_explain_video_mcp.logging_conf import configure_logging
from code_explain_video_mcp.server import run

# CLI flags that override a settings field of the same name.
OVERRIDABLE = ("transport", "host", "port", "dry_run")


def main(argv: Sequence[str] | None = None) -> int:
    """Parse args, build the server, and block on the chosen transport.

    Flags outrank the config file and the ``CODE_EXPLAIN_VIDEO_*`` env vars,
    extending the precedence ladder in
    :func:`code_explain_video_mcp.config.load_settings`.
    """
    parser = argparse.ArgumentParser(
        prog="code-explain-video-mcp",
        description=(
            "MCP server that turns a codebase scope plus a goal into a rendered "
            "Remotion explainer video."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http", "sse"),
        default=None,
        help="Transport to serve on. Defaults to stdio, which is what Claude Code "
        "and Codex spawn. Use http to attach a client over the network.",
    )
    parser.add_argument("--host", default=None, help="Bind address for http/sse (not a URL).")
    parser.add_argument("--port", type=int, default=None, help="Port for http/sse.")
    parser.add_argument("--config", type=Path, default=None, help="Path to a TOML settings file.")
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run the pipeline with placeholder stage bodies (no LLM, no tsc, no "
        "render). On by default while those stages are unimplemented.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
    )
    args = parser.parse_args(argv)

    configure_logging(args.log_level, stdio_safe=True)

    settings = load_settings(args.config)
    overrides = {
        name: value for name in OVERRIDABLE if (value := getattr(args, name)) is not None
    }

    try:
        run(replace(settings, **overrides))
    except KeyboardInterrupt:  # pragma: no cover - interactive
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
