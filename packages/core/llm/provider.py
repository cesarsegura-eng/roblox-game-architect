"""The LLMProvider interface (ADR-0003). Agents depend on this and nothing else."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import CostQuote, GenerationRequest, GenerationResponse


@runtime_checkable
class LLMProvider(Protocol):
    """A text generator. Adapters hold the SDK call and no decision logic."""

    name: str

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Return the model's text for `request`, or raise `LLMError`."""
        ...

    def quote_max_cost(self, request: GenerationRequest) -> CostQuote | None:
        """Upper bound on the cost of `generate(request)`, or None if none is reliable.

        None means "cannot bound this call"; a spend cap must then refuse it.
        A returned bound is a promise: `generate` must not cost more.
        """
        ...
