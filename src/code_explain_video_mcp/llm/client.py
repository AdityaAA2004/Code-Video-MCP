"""Provider-agnostic LLM interface.

``LLMClient`` is a Protocol so the pipeline depends on a shape, not a vendor SDK.
Two implementations are expected: a real provider-backed client, and a canned
client for tests that replays fixtures.

Structured output is a first-class method rather than "parse the text and hope":
``build_storyboard`` must produce a document that validates against the
storyboard schema, so schema enforcement belongs at this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar, runtime_checkable

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


@dataclass(frozen=True, slots=True)
class StructuredRequest:
    """A request that must come back conforming to ``response_model``."""

    system: str
    prompt: str
    response_model: type[BaseModel]
    model: str
    max_output_tokens: int
    temperature: float


@runtime_checkable
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
        request: StructuredRequest,
        response_model: type[ModelT],
    ) -> ModelT:
        """Generation constrained to a schema, used by ``build_storyboard``.

        Implementations are responsible for retrying provider-side schema
        violations before surfacing a failure.
        """
        ...


class ProviderLLMClient:
    """Real client. Owns credentials, retries, timeouts, and rate-limit backoff."""

    def __init__(self, api_key: str | None = None, *, base_url: str | None = None) -> None:
        raise NotImplementedError

    async def complete(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        max_output_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        raise NotImplementedError

    async def complete_structured(
        self,
        request: StructuredRequest,
        response_model: type[ModelT],
    ) -> ModelT:
        raise NotImplementedError


class RecordedLLMClient:
    """Fixture-replaying client for tests; never touches the network."""

    def __init__(self, fixtures_dir: str) -> None:
        raise NotImplementedError

    async def complete(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        max_output_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        raise NotImplementedError

    async def complete_structured(
        self,
        request: StructuredRequest,
        response_model: type[ModelT],
    ) -> ModelT:
        raise NotImplementedError
