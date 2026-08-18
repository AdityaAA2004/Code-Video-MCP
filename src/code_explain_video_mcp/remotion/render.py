"""Shelling out to the Remotion CLI.

The last pipeline stage and the only one measured in minutes, which is why the
job store exists. Two properties this module must hold:

* the render runs against the *job workspace copy*, never the checked-in
  scaffold, so two concurrent jobs cannot corrupt each other;
* the subprocess is killed on timeout or cancellation. An orphaned ``chromium``
  from a Remotion render will happily sit at 100% CPU forever.

Not implemented: ``graph.nodes`` stands in for this stage under ``dry_run``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from code_explain_video_mcp.config import RenderSettings


@dataclass(frozen=True, slots=True)
class RenderResult:
    """What came out of ``npx remotion render``."""

    video_path: Path
    duration_seconds: float
    size_bytes: int
    frames: int
    elapsed_seconds: float
    stdout_tail: str = ""
    """Last few lines of CLI output, kept for the job log on failure."""

    warnings: list[str] = field(default_factory=list)


async def ensure_dependencies_installed(
    project_dir: Path, settings: RenderSettings
) -> None:
    """Run the package manager's install step in the job's project copy.

    Separated from :func:`render_video` because it is the slow, cacheable half —
    a future optimisation shares one ``node_modules`` across jobs instead of
    installing per job.

    Raises:
        ExternalToolError: ``node``/``npx`` is not on PATH.
    """
    raise NotImplementedError


async def render_video(
    project_dir: Path,
    output_path: Path,
    settings: RenderSettings,
    *,
    job_id: str | None = None,
) -> RenderResult:
    """Render ``settings.composition_id`` from ``project_dir`` to ``output_path``.

    Raises:
        RenderError: The CLI exited non-zero, timed out, or wrote no file.
        ExternalToolError: ``node``/``npx`` is not on PATH.
    """
    raise NotImplementedError
