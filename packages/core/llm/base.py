"""The project's own LLM interface (ADR-0003).

Agents depend on this module only. No vendor SDK is imported here or in agent
code; each real provider gets a thin adapter that translates to and from these
types and does nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

Role = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class UntrustedBlock:
    """Project content the agent read (invariant I3).

    Travels in its own labelled channel, separate from `system` and `messages`,
    so an adapter can fence it as data and never present it as instructions.
    """

    label: str
    content: str


@dataclass(frozen=True, slots=True)
class LLMRequest:
    system: str
    messages: tuple[Message, ...]
    untrusted: tuple[UntrustedBlock, ...] = ()
    max_tokens: int = 1024
    # Providers differ on sampling; 0.0 is the only value every adapter honours.
    temperature: float = 0.0


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    model: str
    usage: Usage = field(default_factory=Usage)


class LLMProviderError(Exception):
    """Raised by any provider for a failure the caller may want to handle."""


@runtime_checkable
class LLMProvider(Protocol):
    """What an agent may ask of a language model, and nothing more."""

    @property
    def name(self) -> str: ...

    def complete(self, request: LLMRequest) -> LLMResponse: ...
