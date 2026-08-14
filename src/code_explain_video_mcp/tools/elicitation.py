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
from typing import TYPE_CHECKING

from code_explain_video_mcp.tools.schemas import ScopeMode

if TYPE_CHECKING:
    from fastmcp import Context


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    """Outcome of the ladder above."""

    scope: str | None
    """Path or glob, or ``None`` meaning the whole repo."""

    mode: ScopeMode
    notes: list[str]
    """Caveats to echo to the user, e.g. that whole-repo was defaulted."""


def supports_elicitation(ctx: "Context | None") -> bool:
    """Report whether this connection can be asked a question.

    Checks negotiated client capabilities rather than assuming; returns ``False``
    for a missing context so non-MCP callers (tests, CLI) work unchanged.
    """
    raise NotImplementedError


async def elicit_scope(ctx: "Context") -> ScopeDecision:
    """Ask the user whether to cover the whole repo or a specific path.

    Handles all three elicitation outcomes — accept, decline, cancel — by
    falling back to :func:`default_scope` for decline and cancel rather than
    raising, so a user dismissing the prompt still gets a video.
    """
    raise NotImplementedError


def scope_from_attached_context(ctx: "Context | None") -> ScopeDecision | None:
    """Derive scope from whatever the host attached to the conversation.

    Returns ``None`` when nothing usable is attached, which advances the ladder
    to :func:`default_scope`.
    """
    raise NotImplementedError


def default_scope(reason: str) -> ScopeDecision:
    """Return the whole-repo fallback with an explicit user-facing note."""
    raise NotImplementedError


async def resolve_requested_scope(
    scope: str | None,
    ctx: "Context | None",
    *,
    allow_elicitation: bool = True,
) -> ScopeDecision:
    """Run the full ladder and return the decision. Never raises for a missing scope."""
    raise NotImplementedError
