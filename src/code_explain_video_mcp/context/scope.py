"""Turning "this file" / "this folder" / "the whole repo" into a bounded file list.

The architecture doc is explicit that a hard ceiling must be decided up front,
so the cap is not optional or best-effort: the walk prunes known-noise
directories, ranks what survives, and truncates to ``ScopeSettings.max_files``
and ``max_total_bytes``. Truncation is recorded on the result so the tool layer
can tell the user their repo was sampled rather than covered.

Ranking exists because "top N by size" is a poor proxy for "N most explanatory
files" — import centrality (how many other selected files import this one) is
the better default for a repo-level overview.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from code_explain_video_mcp.config import ScopeSettings


@dataclass(frozen=True, slots=True)
class SelectedFile:
    """One file that made the cut, with the score that got it there."""

    path: Path
    """Absolute path on disk."""

    relative_path: str
    """Repo-relative path; this is what appears in snippets and narration."""

    size_bytes: int
    language: str | None
    score: float
    """Ranking score; interpretation depends on ``ranking_strategy``."""


@dataclass(frozen=True, slots=True)
class ResolvedScope:
    """The bounded answer to "what are we explaining?"."""

    root: Path
    requested: str | None
    """Raw scope string as given, or ``None`` for whole-repo."""

    is_whole_repo: bool
    files: list[SelectedFile]
    total_bytes: int
    truncated: bool
    """True when the caps dropped files that would otherwise have been included."""

    dropped_file_count: int
    summary: str
    """One-line human description, echoed in the tool response."""

    notes: list[str] = field(default_factory=list)


def resolve_scope(
    root: Path,
    requested: str | None,
    settings: ScopeSettings,
) -> ResolvedScope:
    """Resolve a path/glob (or whole repo) into a capped, ranked file list.

    Raises:
        ScopeResolutionError: ``requested`` matches nothing, or matches only
            files excluded by the noise filters.
    """
    raise NotImplementedError


def walk_repo(root: Path, settings: ScopeSettings) -> list[Path]:
    """Walk ``root``, pruning excluded directories and glob patterns as it goes.

    Pruning happens during traversal, not after, so ``node_modules`` is never
    descended into.
    """
    raise NotImplementedError


def is_excluded(path: Path, root: Path, settings: ScopeSettings) -> bool:
    """Whether a path is noise: vendored deps, VCS, build output, lockfiles, binaries."""
    raise NotImplementedError


def rank_files(paths: list[Path], root: Path, settings: ScopeSettings) -> list[SelectedFile]:
    """Score and sort candidates by the configured ranking strategy."""
    raise NotImplementedError


def import_centrality(paths: list[Path], root: Path) -> dict[Path, float]:
    """Score each file by how many other candidates import it.

    A cheap static pass (regex/AST over import statements), not a real
    dependency graph — enough to float entrypoints and core modules to the top.
    """
    raise NotImplementedError


def detect_language(path: Path) -> str | None:
    """Map a file extension to a syntax-highlighter language id."""
    raise NotImplementedError
