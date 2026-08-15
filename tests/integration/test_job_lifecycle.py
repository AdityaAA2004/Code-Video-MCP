"""The async job contract, end to end through the real MCP tools.

What these lock in is the load-bearing promise of the architecture:
``explain_codebase`` returns a handle immediately and the work happens
elsewhere. If that ever regresses into a blocking call, a multi-minute render
would freeze the host — so the timing assertion here is a real test, not a
formality.

Everything runs over FastMCP's in-memory transport: no subprocess, no port.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastmcp import Client

from code_explain_video_mcp.config import load_settings
from code_explain_video_mcp.server import create_server

REPO_ROOT = Path(__file__).resolve().parents[2]
TERMINAL = {"succeeded", "failed", "cancelled"}


@pytest.fixture
def settings(tmp_path: Path):
    """Server settings pointed at a throwaway workspace root."""
    base = load_settings()
    return replace(
        base,
        dry_run=True,
        render=replace(
            base.render,
            workspace_root=tmp_path / "workspaces",
            output_root=tmp_path / "output",
        ),
    )


async def _drain(client: Client, job_id: str, timeout: float = 120.0):
    """Poll until the job reaches a terminal status; return the final status."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = (await client.call_tool("get_render_status", {"job_id": job_id})).data
        if status.status in TERMINAL:
            return status
        await asyncio.sleep(0.2)
    pytest.fail(f"job {job_id} did not finish within {timeout}s")


async def test_exposes_exactly_three_tools(settings) -> None:
    """The MCP surface is capped at three by design; a fourth is a design change."""
    async with Client(create_server(settings)) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == {"explain_codebase", "get_render_status", "get_storyboard"}


async def test_explain_codebase_returns_immediately(settings) -> None:
    """The tool must not await the pipeline, which takes far longer than this."""
    async with Client(create_server(settings)) as client:
        started = time.monotonic()
        result = await client.call_tool(
            "explain_codebase",
            {"goal": "test", "scope": "src/code_explain_video_mcp/jobs", "root": str(REPO_ROOT)},
        )
        elapsed = time.monotonic() - started

        assert result.data.job_id
        assert result.data.status == "queued"
        assert elapsed < 2.0, f"tool blocked for {elapsed:.1f}s; it must return a handle"
        await _drain(client, result.data.job_id)


async def test_job_runs_every_stage_to_success(settings) -> None:
    async with Client(create_server(settings)) as client:
        job = (
            await client.call_tool(
                "explain_codebase",
                {"goal": "test", "scope": "src/code_explain_video_mcp/jobs", "root": str(REPO_ROOT)},
            )
        ).data
        final = await _drain(client, job.job_id)

    assert final.status == "succeeded"
    assert final.stage == "complete"
    assert final.progress == 1.0
    assert final.stage_index == final.total_stages


async def test_dry_run_is_disclosed_in_notes(settings) -> None:
    """A placeholder result must never be presentable as a finished video."""
    async with Client(create_server(settings)) as client:
        job = (
            await client.call_tool(
                "explain_codebase",
                {"goal": "test", "scope": "src/code_explain_video_mcp/jobs", "root": str(REPO_ROOT)},
            )
        ).data
        assert any("DRY RUN" in note for note in job.notes)
        final = await _drain(client, job.job_id)
    assert "DRY RUN" in (final.message or "")


async def test_storyboard_is_readable_before_the_job_finishes(settings) -> None:
    """The stage-3 escape hatch: the plan is useful before the render lands."""
    async with Client(create_server(settings)) as client:
        job = (
            await client.call_tool(
                "explain_codebase",
                {"goal": "test", "scope": "src/code_explain_video_mcp/jobs", "root": str(REPO_ROOT)},
            )
        ).data

        seen_early = False
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            status = (
                await client.call_tool("get_render_status", {"job_id": job.job_id})
            ).data
            if status.storyboard_available and status.status not in TERMINAL:
                board = (
                    await client.call_tool("get_storyboard", {"job_id": job.job_id})
                ).data
                assert board.storyboard.scenes
                assert board.storyboard.total_duration_seconds > 0
                # Computed fields must survive serialization to the host.
                assert board.storyboard.total_frames > 0
                assert board.markdown.startswith("#")
                seen_early = True
                break
            if status.status in TERMINAL:
                break
            await asyncio.sleep(0.1)

        assert seen_early, "storyboard never became available before the job ended"
        await _drain(client, job.job_id)


async def test_unknown_job_id_is_an_error(settings) -> None:
    async with Client(create_server(settings)) as client:
        with pytest.raises(Exception, match="job_does_not_exist"):
            await client.call_tool("get_render_status", {"job_id": "job_does_not_exist"})


async def test_missing_root_from_non_repo_cwd_fails_fast(settings, tmp_path, monkeypatch) -> None:
    """No job should be created when the root cannot be determined."""
    monkeypatch.chdir(tmp_path)
    async with Client(create_server(settings)) as client:
        with pytest.raises(Exception, match="root"):
            await client.call_tool("explain_codebase", {"goal": "no root anywhere"})
