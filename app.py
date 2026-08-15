"""Convenience entrypoint: ``.venv/bin/python app.py``.

The real server lives in :mod:`code_explain_video_mcp.server`. This file exists
only so the repo root still has an obvious "run the thing" script; it holds no
logic and defines no tools of its own.

The spike that used to live here registered a fourth tool (``explain_code``)
directly on a module-level ``FastMCP``. Both parts of that were wrong: the MCP
surface is capped at three tools by design, and a module-level instance defeats
the ``create_server`` factory that injects settings, the job store, and the
compiled graph.

Defaults to HTTP on 127.0.0.1:8000 because that is the useful mode for a human
poking at it with ``app_client.py --url``. Claude Code and Codex spawn the
server over **stdio** instead — see ``.mcp.json`` and the README — which is what
``python -m code_explain_video_mcp`` defaults to.
"""

from __future__ import annotations

import sys

from code_explain_video_mcp.__main__ import main

if __name__ == "__main__":
    argv = sys.argv[1:]
    if not any(arg.startswith("--transport") for arg in argv):
        argv = ["--transport", "http", *argv]
    raise SystemExit(main(argv))
