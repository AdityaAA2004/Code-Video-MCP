"""What a pipeline node is allowed to reach for.

Nodes are built as closures over a :class:`PipelineDeps` instance rather than
importing a module-level store or settings object. Two reasons:

* the graph is compiled once in ``create_server`` and needs the *server's*
  store, not a global one;
* a test can compile the same graph over a throwaway store and a ``Settings``
  with tiny caps, with no server process anywhere.

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
