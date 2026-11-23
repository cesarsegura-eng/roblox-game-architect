"""Typed values for text generation.

Trusted instructions and untrusted content are different types on purpose
(invariant I3, docs/safety.md). A request holds them in separate fields, so
nothing downstream has to guess which strings may be obeyed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

FinishReason = Literal["stop", "length"]

DEFAULT_MAX_OUTPUT_TOKENS = 1024


class LLMError(Exception):
    """Base class for every error raised by the llm package."""


class InvalidRequestError(LLMError, ValueError):
    """The request is malformed. Raised at construction, before any provider runs."""


class InvalidCostError(LLMError, ValueError):
    """A cost or cost bound is not a finite, non-negative Decimal."""


@dataclass(frozen=True, slots=True)
class TrustedInstruction:
    """Text written by this project's own code. The only text a model may obey.

    Never build one from project content, user files or model output.
    """

    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise InvalidRequestError("TrustedInstruction.text must be a non-empty string")


@dataclass(frozen=True, slots=True)
class UntrustedContent:
    """Data the agent read (scripts, instance names, descriptions, tool output).

    `source` says where it came from, for labelling only. The content is data to
    analyse and is never an instruction, whatever it says.
    """

    source: str
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise InvalidRequestError("UntrustedContent.source must be a non-empty string")
        if not isinstance(self.text, str):
            raise InvalidRequestError("UntrustedContent.text must be a string")


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """One text-generation call.

    `instructions` is the trusted channel; `untrusted` is the labelled data
    channel. Plain strings are rejected in both so a caller cannot slip
    untrusted text into the trusted field by accident.
    """

    instructions: tuple[TrustedInstruction, ...]
    untrusted: tuple[UntrustedContent, ...] = ()
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    def __post_init__(self) -> None:
        # Normalise lists to tuples so the frozen request is really immutable.
        object.__setattr__(self, "instructions", tuple(self.instructions))
        object.__setattr__(self, "untrusted", tuple(self.untrusted))
        if not self.instructions:
            raise InvalidRequestError("a request needs at least one TrustedInstruction")
        if not all(isinstance(i, TrustedInstruction) for i in self.instructions):
            raise InvalidRequestError("instructions must be TrustedInstruction values")
        if not all(isinstance(u, UntrustedContent) for u in self.untrusted):
            raise InvalidRequestError("untrusted must be UntrustedContent values")
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or self.max_output_tokens < 1
        ):
            raise InvalidRequestError("max_output_tokens must be a positive integer")


def _require_money(value: object, label: str) -> None:
    """Amounts are exact `Decimal`s: finite and non-negative. Floats are rejected."""
    if not isinstance(value, Decimal):
        raise InvalidCostError(f"{label} must be a Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise InvalidCostError(f"{label} must be finite, got {value}")
    if value < 0:
        raise InvalidCostError(f"{label} must not be negative, got {value}")


@dataclass(frozen=True, slots=True)
class Usage:
    """Token counts and the real cost of a call. The spend cap (I6) reads `cost_usd`."""

    input_tokens: int
    output_tokens: int
    cost_usd: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        _require_money(self.cost_usd, "Usage.cost_usd")


@dataclass(frozen=True, slots=True)
class CostQuote:
    """A provider's upper bound, in USD, on what one call can cost.

    The bound is a promise by the provider adapter, made before the call runs.
    """

    max_usd: Decimal

    def __post_init__(self) -> None:
        _require_money(self.max_usd, "CostQuote.max_usd")


@dataclass(frozen=True, slots=True)
class GenerationResponse:
    """Model output. Untrusted: it is generated text, not a trusted instruction."""

    text: str
    provider: str
    model: str
    usage: Usage
    finish_reason: FinishReason = "stop"
