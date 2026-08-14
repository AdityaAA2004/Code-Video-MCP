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


def build_arg_parser() -> argparse.ArgumentParser:
    """Define CLI flags: ``--transport``, ``--host``, ``--port``, ``--config``.

    Flags override values from the config file, matching the precedence in
    :func:`code_explain_video_mcp.config.load_settings`.
    """
    raise NotImplementedError


def main(argv: Sequence[str] | None = None) -> int:
    """Parse args, build the server, and block on the chosen transport."""
    raise NotImplementedError


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
