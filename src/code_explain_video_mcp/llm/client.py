"""Provider-agnostic LLM interface.

FastMCP 4 removed ``ctx.sample()`` (server-initiated sampling through the host),
so a server that needs a model must call one itself: this package owns a direct
provider client and its own credentials rather than borrowing the host's model.

``LLMClient`` is a Protocol so the pipeline depends on a shape, not a vendor SDK,
and tests can substitute a canned client without touching the network. Nothing
implements it yet — the pipeline runs with ``Settings.dry_run`` until it does.

Structured output is a first-class method rather than "parse the text and hope":
``build_storyboard`` must produce a document that validates against the
storyboard schema, so schema enforcement belongs at this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """A completed generation plus the accounting the job store reports."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    """What the pipeline needs from a model provider."""

    async def complete(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        max_output_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Free-form generation, used by codegen and the repair pass."""
        ...

    async def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        max_output_tokens: int,
        temperature: float,
        response_model: type[ModelT],
    ) -> ModelT:
        """Generation constrained to a schema, used by ``build_storyboard``.

        Implementations own retrying provider-side schema violations before
        surfacing a failure.
        """
        ...
