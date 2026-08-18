"""Per-job working directories.

Each job gets its own directory so that a Remotion scaffold copy, the generated
TSX, the ``tsc`` output, the job log, and the rendered MP4 for one job can never
collide with another's. Cleanup is TTL-based rather than immediate because the
most useful time to read a job's workspace is right after it fails.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from code_explain_video_mcp.config import RenderSettings
from code_explain_video_mcp.logging_conf import get_logger

logger = get_logger("jobs.workspace")

@dataclass(frozen=True, slots=True)
class Workspace:
    """One job's directory, with the well-known paths inside it named."""

    job_id: str
    root: Path

    @property
    def project_dir(self) -> Path:
        """The Remotion scaffold copy that gets type-checked and rendered."""
        return self.root / "project"

    @property
    def output_dir(self) -> Path:
        """Where render artifacts land before being published."""
        return self.root / "out"

    @property
    def storyboard_path(self) -> Path:
        """The storyboard JSON, written to disk so a failed job is inspectable."""
        return self.root / "storyboard.json"

    @property
    def video_path(self) -> Path:
        """Conventional location of the rendered MP4."""
        return self.output_dir / "explainer.mp4"


class WorkspaceManager:
    """Creates and reaps job workspaces under ``RenderSettings.workspace_root``."""

    def __init__(self, settings: RenderSettings) -> None:
        self._settings = settings

    @property
    def root(self) -> Path:
        """Parent directory holding every job workspace."""
        return self._settings.workspace_root

    def create(self, job_id: str) -> Workspace:
        """Make (and return) a fresh workspace for ``job_id``."""
        workspace = Workspace(job_id=job_id, root=self.root / job_id)
        workspace.root.mkdir(parents=True, exist_ok=True)
        workspace.output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("workspace at %s", workspace.root, extra={"job_id": job_id})
        return workspace

    def reap(self, ttl_seconds: float, *, keep: set[str] | None = None) -> list[str]:
        """Delete workspaces whose mtime is older than ``ttl_seconds``.

        ``keep`` protects jobs that are still running — their directories may be
        untouched for a long stretch during a slow render and must not be
        collected out from under them.
        """
        if not self.root.is_dir():
            return []
        protected = keep or set()
        cutoff = time.time() - ttl_seconds
        removed: list[str] = []
        for child in self.root.iterdir():
            if not child.is_dir() or child.name in protected:
                continue
            try:
                if child.stat().st_mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
                    removed.append(child.name)
            except OSError:  # pragma: no cover - racing another reaper
                continue
        if removed:
            logger.info("reaped %d expired workspace(s)", len(removed))
        return removed
