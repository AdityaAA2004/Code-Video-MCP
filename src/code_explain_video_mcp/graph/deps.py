"""What a pipeline node is allowed to reach for.

Nodes close over a :class:`PipelineDeps` instead of importing a module-level
store or settings object, so the graph compiled in ``create_server`` uses the
*server's* store, and a test can compile the same graph over a throwaway store
and a ``Settings`` with tiny caps.

Nothing job-specific lives here — the ``job_id`` travels in the graph state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from code_explain_video_mcp.config import Settings
    from code_explain_video_mcp.jobs.store import JobStore
    from code_explain_video_mcp.jobs.workspace import WorkspaceManager


@dataclass(frozen=True, slots=True)
class PipelineDeps:
    """Server-scoped collaborators shared by every node."""

    settings: "Settings"
    store: "JobStore"
    workspaces: "WorkspaceManager"
