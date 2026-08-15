"""End-to-end exercise of the three MCP tools against a live server.

This is the harness that proves the async job contract works: one
``explain_codebase`` call returns a ``job_id`` in milliseconds, repeated
``get_render_status`` polls show the pipeline moving through its stages, and
``get_storyboard`` becomes answerable partway through — before the job is done.

Two modes:

* ``--in-process`` (default) constructs the server object and talks to it over
  FastMCP's in-memory transport. No subprocess, no port, nothing to clean up.
* ``--url http://127.0.0.1:8000/mcp`` talks to a server already running over
  HTTP, which is how you check that the transport wiring works rather than just
  the tool logic.

Usage::

    .venv/bin/python app_client.py
    .venv/bin/python app_client.py --scope src/code_explain_video_mcp/graph
    .venv/bin/python app_client.py --url http://127.0.0.1:8000/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from fastmcp import Client

POLL_INTERVAL_SECONDS = 0.75
POLL_TIMEOUT_SECONDS = 180.0


def build_client(url: str | None) -> Client:
    """Return a client bound either to a URL or to an in-process server object."""
    if url:
        return Client(url)
    from code_explain_video_mcp.config import load_settings
    from code_explain_video_mcp.server import create_server

    return Client(create_server(load_settings()))


async def run(args: argparse.Namespace) -> int:
    """Start a job, poll it to completion, and print what each tool returned."""
    client = build_client(args.url)

    async with client:
        listed = await client.list_tools()
        print(f"connected — {len(listed)} tools: {', '.join(t.name for t in listed)}")
        print()

        started = time.monotonic()
        result = await client.call_tool(
            "explain_codebase",
            {"goal": args.goal, "scope": args.scope, "root": args.root},
        )
        job = result.data
        elapsed_ms = (time.monotonic() - started) * 1000

        print(f"explain_codebase returned in {elapsed_ms:.0f} ms")
        print(f"  job_id     : {job.job_id}")
        print(f"  scope_mode : {job.scope_mode}")
        print(f"  scope      : {job.resolved_scope_summary}")
        print(f"  stages     : {job.total_stages}")
        for note in job.notes:
            print(f"  note       : {note}")
        print()

        if elapsed_ms > 2000:
            print("  WARNING: the tool call blocked for over 2s — it should return immediately.")
            print()

        storyboard_seen = False
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        last_stage = None

        while time.monotonic() < deadline:
            status = (await client.call_tool("get_render_status", {"job_id": job.job_id})).data

            if status.stage != last_stage:
                bar_width = 24
                filled = int(status.progress * bar_width)
                bar = "#" * filled + "." * (bar_width - filled)
                print(
                    f"  [{bar}] {status.progress * 100:3.0f}%  "
                    f"{status.stage_index}/{status.total_stages}  "
                    f"{status.stage:<24} {status.message or ''}"
                )
                last_stage = status.stage

            # The escape hatch: the storyboard is readable long before the render.
            if status.storyboard_available and not storyboard_seen:
                storyboard_seen = True
                sb = (await client.call_tool("get_storyboard", {"job_id": job.job_id})).data
                print()
                print(
                    f"  get_storyboard answered mid-flight at stage "
                    f"'{status.stage}' (editable={sb.editable})"
                )
                print(
                    f"    {len(sb.storyboard.scenes)} scenes, "
                    f"{sb.storyboard.total_duration_seconds:g}s, "
                    f"{sb.storyboard.total_frames} frames"
                )
                for scene in sb.storyboard.scenes[:4]:
                    print(f"      - {scene.id:<12} {scene.title}")
                if len(sb.storyboard.scenes) > 4:
                    print(f"      ... {len(sb.storyboard.scenes) - 4} more")
                print()

            if status.status in ("succeeded", "failed", "cancelled"):
                total = time.monotonic() - started
                print()
                print(f"job {status.status} after {total:.1f}s")
                if status.error:
                    print(f"  error: {status.error}")
                if status.artifact:
                    print(f"  local_path: {status.artifact.local_path}")
                    print(f"  duration  : {status.artifact.duration_seconds}s")
                if status.message:
                    print(f"  message   : {status.message}")
                return 0 if status.status == "succeeded" else 1

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        print(f"timed out after {POLL_TIMEOUT_SECONDS}s waiting for the job to finish")
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=None,
        help="Talk to a running HTTP server instead of an in-process one, "
        "e.g. http://127.0.0.1:8000/mcp",
    )
    parser.add_argument(
        "--goal",
        default="Understand how a job flows through the LangGraph pipeline.",
        help="The goal threaded into every scene.",
    )
    parser.add_argument("--scope", default=None, help="Path or glob. Omit for whole repo.")
    parser.add_argument(
        "--root", default=str(Path(__file__).parent.resolve()), help="Repo root."
    )
    return asyncio.run(run(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
