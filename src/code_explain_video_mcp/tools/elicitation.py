"""Deciding what to explain when the host did not say.

Client compatibility is a code concern here, not a docs concern. Elicitation
works in Claude Code CLI, does not work in Claude Desktop, and is unconfirmed
elsewhere — so every path through this module must terminate in a usable scope
even when no question can be asked.

The ladder, highest confidence first:

1. ``scope`` argument given explicitly -> use it.
2. Client supports elicitation -> ask "whole repo or a specific path?".
3. Something is attached in the host's context -> use that.
4. Nothing else -> whole repo, and set a note that MUST be surfaced to the user
   verbatim so they know the server chose for them.

FastMCP 4 has two elicitation mechanisms depending on the negotiated protocol
era: ``await ctx.elicit(...)`` on handshake-era connections (<= 2025-11-25), and
the return-and-resume guard pattern (return ``InputRequiredResult``, re-read
``ctx.input_responses`` on the next call) on 2026-07-28+. Since neither is
guaranteed, both are probed behind :func:`supports_elicitation` and both fall
through to the same non-interactive default.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from code_explain_video_mcp.context.scope import find_repo_root, looks_like_repo, repo_markers_at
from code_explain_video_mcp.errors import RootResolutionError
from code_explain_video_mcp.logging_conf import get_logger
from code_explain_video_mcp.tools.schemas import ScopeMode

if TYPE_CHECKING:
    from fastmcp import Context

logger = get_logger("tools.elicitation")

RootMode = Literal["explicit", "configured", "cwd", "cwd_ancestor"]

WHOLE_REPO_CHOICE = "the whole repository"
"""Label for the whole-repo option; matched case-insensitively on the way back."""

DEFAULTED_NOTE = (
    "No scope was given and this client could not be asked, so the whole "
    "repository was used. Re-run explain_codebase with an explicit `scope` "
    "(a path or a glob) to narrow it."
)


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    """Outcome of the ladder above."""

    scope: str | None
    """Path or glob, or ``None`` meaning the whole repo."""

    mode: ScopeMode
    notes: list[str]
    """Caveats to echo to the user, e.g. that whole-repo was defaulted."""


@dataclass(frozen=True, slots=True)
class RootDecision:
    """Which repo root a job will run against, and how that was decided."""

    root: Path
    mode: RootMode
    notes: list[str]


def resolve_root(root: str | None, default_root: Path | None = None) -> RootDecision:
    """Decide the repo root, or refuse rather than guess wrong.

    The ladder, highest confidence first:

    1. ``root`` given explicitly -> use it (must exist and be a directory).
    2. ``default_root`` configured on the server -> use it.
    3. The process cwd, if it looks like a repo root.
    4. The nearest ancestor of cwd that looks like a repo root.
    5. Nothing -> raise.

    Rung 5 is the point of this function. A stdio server inherits its *host's*
    working directory, so an omitted ``root`` previously meant "explain whatever
    directory Claude Code or Codex happened to launch from" — which silently
    produces a video about the wrong codebase. Silently wrong is the worst
    outcome available here, so an unresolvable root is a hard, immediate error
    with instructions the calling model can act on.

    Raises:
        RootResolutionError: The explicit/configured path is unusable, or no
            repo root could be inferred from the cwd.
    """
    if root and root.strip():
        candidate = Path(root.strip()).expanduser()
        resolved = candidate.resolve()
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
        return RootDecision(root=resolved, mode="explicit", notes=notes)

    if default_root is not None:
        resolved = Path(default_root).expanduser().resolve()
        if not resolved.is_dir():
            raise RootResolutionError(
                f"Configured default_root {resolved} is not a directory. Fix "
                "CODE_EXPLAIN_VIDEO_DEFAULT_ROOT in this server's MCP configuration."
            )
        logger.info("using configured default_root %s", resolved)
        return RootDecision(root=resolved, mode="configured", notes=[])

    cwd = Path.cwd().resolve()
    if looks_like_repo(cwd):
        markers = ", ".join(repo_markers_at(cwd)[:3])
        logger.info("using cwd %s as root (markers: %s)", cwd, markers)
        return RootDecision(
            root=cwd,
            mode="cwd",
            notes=[
                f"No `root` was given, so this server's working directory was used: "
                f"{cwd} (identified by {markers}). If that is not the repository you "
                "meant, re-run explain_codebase with an explicit `root`."
            ],
        )

    ancestor = find_repo_root(cwd)
    if ancestor is not None:
        markers = ", ".join(repo_markers_at(ancestor)[:3])
        logger.info("walked up from %s to repo root %s", cwd, ancestor)
        return RootDecision(
            root=ancestor,
            mode="cwd_ancestor",
            notes=[
                f"No `root` was given. This server's working directory ({cwd}) is not "
                f"a repository root, so its nearest enclosing one was used: {ancestor} "
                f"(identified by {markers}). If that is not the repository you meant, "
                "re-run explain_codebase with an explicit `root`."
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

    Checks negotiated client capabilities rather than assuming; returns ``False``
    for a missing context so non-MCP callers (tests, CLI) work unchanged.

    The attribute walk is defensive on purpose. The location of the negotiated
    capabilities has moved between MCP protocol revisions, and guessing wrong
    must degrade to "cannot ask" rather than raise — a server that crashes
    because it could not find a capability flag is strictly worse than one that
    silently falls back to the whole repo.
    """
    if ctx is None:
        return False
    try:
        session = getattr(ctx, "session", None)
        params = getattr(session, "client_params", None)
        capabilities = getattr(params, "capabilities", None)
        if capabilities is not None and getattr(capabilities, "elicitation", None) is not None:
            return True
    except Exception:  # noqa: BLE001 - capability probing must never break a call
        logger.debug("elicitation capability probe raised; treating as unsupported")
        return False
    return False


async def elicit_scope(ctx: "Context") -> ScopeDecision:
    """Ask the user whether to cover the whole repo or a specific path.

    Handles all three elicitation outcomes — accept, decline, cancel — by
    falling back to :func:`default_scope` for decline and cancel rather than
    raising, so a user dismissing the prompt still gets a video.
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
        return ScopeDecision(scope=None, mode="whole_repo", notes=["You chose the whole repository."])

    logger.info("elicited scope: %s", answer)
    return ScopeDecision(scope=answer, mode="explicit", notes=[])


def scope_from_attached_context(ctx: "Context | None") -> ScopeDecision | None:
    """Derive scope from whatever the host attached to the conversation.

    Returns ``None`` when nothing usable is attached, which advances the ladder
    to :func:`default_scope`.

    No host in the current MCP revisions exposes its attached files to a server
    in a standard way, so this rung is a documented no-op rather than a guess:
    inventing a scope from an unstandardised field would silently explain the
    wrong code, which is worse than falling through to a whole-repo default that
    announces itself.
    """
    return None


def default_scope(reason: str) -> ScopeDecision:
    """Return the whole-repo fallback with an explicit user-facing note."""
    logger.info("defaulting to whole repo: %s", reason)
    return ScopeDecision(scope=None, mode="whole_repo", notes=[DEFAULTED_NOTE])


async def resolve_requested_scope(
    scope: str | None,
    ctx: "Context | None",
    *,
    allow_elicitation: bool = True,
) -> ScopeDecision:
    """Run the full ladder and return the decision. Never raises for a missing scope."""
    if scope and scope.strip():
        return ScopeDecision(scope=scope.strip(), mode="explicit", notes=[])

    if allow_elicitation and ctx is not None and supports_elicitation(ctx):
        return await elicit_scope(ctx)

    attached = scope_from_attached_context(ctx)
    if attached is not None:
        return attached

    reason = (
        "elicitation is disabled by configuration"
        if not allow_elicitation
        else "this client does not support elicitation"
    )
    return default_scope(reason)
