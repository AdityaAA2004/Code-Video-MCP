"""Console entrypoint: ``python -m code_explain_video_mcp`` / the installed script.

This exists alongside ``fastmcp.json`` on purpose. ``fastmcp run`` is the
preferred path (it owns the environment and transport declaratively), but hosts
that only know how to spawn a command need a plain executable, and that is what
this module provides.

Neither path should contain logic: both converge on
``server.create_server(load_settings(...))``.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path


def build_arg_parser() -> argparse.ArgumentParser:
    """Define CLI flags: ``--transport``, ``--host``, ``--port``, ``--config``.

    Flags override values from the config file, matching the precedence in
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
    parser.add_argument(
        "--config", type=Path, default=None, help="Path to a TOML settings file."
    )
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse args, build the server, and block on the chosen transport."""
    from dataclasses import replace

    from code_explain_video_mcp.config import load_settings
    from code_explain_video_mcp.logging_conf import configure_logging
    from code_explain_video_mcp.server import run

    args = build_arg_parser().parse_args(argv)
    configure_logging(args.log_level, stdio_safe=True)

    settings = load_settings(args.config)
    overrides: dict[str, object] = {}
    if args.transport is not None:
        overrides["transport"] = args.transport
    if args.host is not None:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    if args.dry_run is not None:
        overrides["dry_run"] = args.dry_run
    if overrides:
        settings = replace(settings, **overrides)

    try:
        run(settings)
    except KeyboardInterrupt:  # pragma: no cover - interactive
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
