"""Deciding *which repo* and *which code* to explain when the host did not say.

Two independent ladders live here.

:func:`resolve_root` picks the repository, and its last rung is a hard error.
A stdio server inherits its *host's* working directory, so an omitted ``root``
would otherwise mean "explain whatever directory Claude Code or Codex launched
from" — silently producing a video about the wrong codebase. It never falls back
to "use cwd anyway".

:func:`resolve_requested_scope` picks the code within that repo, and never
raises. Elicitation works in Claude Code CLI, does not work in Claude Desktop,
and is unconfirmed elsewhere, so every rung falls through to a whole-repo
default that announces itself in the notes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from code_explain_video_mcp.errors import RootResolutionError
from code_explain_video_mcp.logging_conf import get_logger
from code_explain_video_mcp.tools.schemas import ScopeMode

if TYPE_CHECKING:
    from fastmcp import Context

logger = get_logger("tools.elicitation")

RootMode = Literal["explicit", "configured", "cwd", "cwd_ancestor"]

VCS_MARKERS: frozenset[str] = frozenset({".git", ".hg", ".svn", ".jj"})
"""Directories that identify a checkout root unambiguously."""

PROJECT_MARKERS: frozenset[str] = frozenset(
    {
        "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
        "package.json", "deno.json", "Cargo.toml", "go.mod", "pom.xml",
        "build.gradle", "build.gradle.kts", "Gemfile", "composer.json",
        "CMakeLists.txt", "mix.exs", "Package.swift",
    }
)
"""Manifests that identify a project root when there is no VCS directory."""

MAX_ROOT_WALK_DEPTH = 25
"""Bound on the upward search, so a pathological path cannot spin."""


def repo_markers_at(path: Path) -> list[str]:
    """Return the VCS/manifest markers directly in ``path``; empty means "not a root"."""
    try:
        names = {entry.name for entry in path.iterdir()}
    except (OSError, PermissionError):
        return []
    return sorted((names & VCS_MARKERS) | (names & PROJECT_MARKERS))


def looks_like_repo(path: Path) -> bool:
    """Whether ``path`` is plausibly the root of a codebase."""
    return bool(repo_markers_at(path))


def find_repo_root(start: Path) -> Path | None:
    """Walk upward from ``start`` looking for a repo root; ``None`` if there is none.

    The home directory and the filesystem root both stop the walk. A stray
    ``package.json`` in ``$HOME`` must never turn "explain the whole repo" into
    "walk the user's entire home directory".
    """
    try:
        current = Path(start).expanduser().resolve()
    except (OSError, RuntimeError):
        return None

    home = Path.home().resolve()
    for _ in range(MAX_ROOT_WALK_DEPTH):
        if current == current.parent:  # filesystem root
            return None
        if current == home:  # check home itself, but never above it
            return current if looks_like_repo(current) else None
        if looks_like_repo(current):
            return current
        current = current.parent
    return None

WHOLE_REPO_CHOICE = "the whole repository"
"""Label for the whole-repo option; matched case-insensitively on the way back."""

DEFAULTED_NOTE = (
    "No scope was given and this client could not be asked, so the whole "
    "repository was used. Re-run explain_codebase with an explicit `scope` "
    "(a path or a glob) to narrow it."
)


@dataclass(frozen=True, slots=True)
class RootDecision:
    """Which repo root a job runs against, how that was decided, and any caveats."""

    root: Path
    mode: RootMode
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    """Which code to cover (``None`` means the whole repo) and any caveats."""

    scope: str | None
    mode: ScopeMode
    notes: list[str] = field(default_factory=list)


def resolve_root(root: str | None, default_root: Path | None = None) -> RootDecision:
    """Decide the repo root, or refuse rather than guess wrong.

    Highest confidence first: explicit ``root`` -> configured ``default_root`` ->
    the cwd if it looks like a repo -> the nearest enclosing repo -> raise.

    Raises:
        RootResolutionError: The explicit/configured path is unusable, or no
            repo root could be inferred from the cwd.
    """
    if root and root.strip():
        resolved = Path(root.strip()).expanduser().resolve()
        if not resolved.exists():
            raise RootResolutionError(
                f"root {root!r} does not exist (resolved to {resolved}). "
                "Pass an absolute path to the repository you want explained."
            )
        if not resolved.is_dir():
            raise RootResolutionError(
                f"root {root!r} is a file, not a directory (resolved to {resolved}). "
                "Pass the repository directory; use `scope` to narrow to one file."
            )
        notes: list[str] = []
        if not looks_like_repo(resolved):
            notes.append(
                f"{resolved} has no VCS directory or project manifest, so it may not "
                "be a repository root. Proceeding with it as given."
            )
        return RootDecision(resolved, "explicit", notes)

    if default_root is not None:
        resolved = Path(default_root).expanduser().resolve()
        if not resolved.is_dir():
            raise RootResolutionError(
                f"Configured default_root {resolved} is not a directory. Fix "
                "CODE_EXPLAIN_VIDEO_DEFAULT_ROOT in this server's MCP configuration."
            )
        logger.info("using configured default_root %s", resolved)
        return RootDecision(resolved, "configured")

    cwd = Path.cwd().resolve()
    inferred = cwd if looks_like_repo(cwd) else find_repo_root(cwd)
    if inferred is not None:
        mode: RootMode = "cwd" if inferred == cwd else "cwd_ancestor"
        markers = ", ".join(repo_markers_at(inferred)[:3])
        logger.info("inferred root %s from cwd %s (%s)", inferred, cwd, mode)
        where = (
            f"this server's working directory was used: {inferred}"
            if mode == "cwd"
            else f"this server's working directory ({cwd}) is not a repository root, "
            f"so its nearest enclosing one was used: {inferred}"
        )
        return RootDecision(
            inferred,
            mode,
            [
                f"No `root` was given, so {where} (identified by {markers}). If that "
                "is not the repository you meant, re-run explain_codebase with an "
                "explicit `root`."
            ],
        )

    raise RootResolutionError(
        f"No `root` was given and none could be inferred: this server's working "
        f"directory is {cwd}, which is not inside any repository (no .git, "
        f"pyproject.toml, package.json, or similar marker was found above it). "
        f"Call explain_codebase again with `root` set to the absolute path of the "
        f"repository you want explained."
    )


def supports_elicitation(ctx: "Context | None") -> bool:
    """Report whether this connection can be asked a question.

    The attribute walk is defensive on purpose: the negotiated capabilities have
    moved between MCP protocol revisions, and guessing wrong must degrade to
    "cannot ask" rather than crash the call. ``None`` context (tests, CLI) is
    likewise just "cannot ask".
    """
    try:
        params = getattr(getattr(ctx, "session", None), "client_params", None)
        capabilities = getattr(params, "capabilities", None)
        return getattr(capabilities, "elicitation", None) is not None
    except Exception:  # noqa: BLE001 - capability probing must never break a call
        logger.debug("elicitation capability probe raised; treating as unsupported")
        return False


def default_scope(reason: str) -> ScopeDecision:
    """The whole-repo fallback, carrying a note the user must be shown."""
    logger.info("defaulting to whole repo: %s", reason)
    return ScopeDecision(None, "whole_repo", [DEFAULTED_NOTE])


def scope_from_attached_context(ctx: "Context | None") -> ScopeDecision | None:
    """Ladder rung 3, deliberately a no-op: ``None`` advances to :func:`default_scope`.

    No current MCP revision exposes a host's attached files to a server in a
    standard way. Inventing a scope from an unstandardised field would silently
    explain the wrong code — worse than a whole-repo default that says so.
    """
    return None


async def elicit_scope(ctx: "Context") -> ScopeDecision:
    """Ask the user for a path or glob, falling back on any non-answer.

    Decline, cancel, and an outright client error all land on
    :func:`default_scope`, so dismissing the prompt still yields a video.
    """
    try:
        result = await ctx.elicit(
            "Which code should the explainer video cover? Enter a path or glob "
            f"relative to the repo root, or '{WHOLE_REPO_CHOICE}' to cover everything.",
            response_type=str,
            response_title="Scope",
        )
    except Exception as exc:  # noqa: BLE001 - an unsupported client can still raise here
        logger.info("elicitation failed (%s); falling back to whole repo", exc)
        return default_scope(f"the client rejected the scope prompt ({type(exc).__name__})")

    action = getattr(result, "action", None)
    if action != "accept":
        return default_scope(f"the user {action or 'dismissed'}ed the scope prompt")

    answer = str(getattr(result, "data", "") or "").strip()
    if not answer or answer.lower() == WHOLE_REPO_CHOICE.lower():
        return ScopeDecision(None, "whole_repo", ["You chose the whole repository."])

    logger.info("elicited scope: %s", answer)
    return ScopeDecision(answer, "explicit")


async def resolve_requested_scope(
    scope: str | None,
    ctx: "Context | None",
    *,
    allow_elicitation: bool = True,
) -> ScopeDecision:
    """Run the scope ladder. Never raises for a missing scope."""
    if scope and scope.strip():
        return ScopeDecision(scope.strip(), "explicit")

    if allow_elicitation and ctx is not None and supports_elicitation(ctx):
        return await elicit_scope(ctx)

    attached = scope_from_attached_context(ctx)
    if attached is not None:
        return attached

    if allow_elicitation:
        return default_scope("this client does not support elicitation")
    return default_scope("elicitation is disabled by configuration")
