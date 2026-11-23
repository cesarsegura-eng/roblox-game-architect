"""Provider-agnostic LLM interface and the fake implementation (ADR-0003)."""

from .fake import FakeProvider
from .provider import LLMProvider
from .registry import UnknownProviderError, create_provider
from .types import (
    CostQuote,
    GenerationRequest,
    GenerationResponse,
    InvalidCostError,
    InvalidRequestError,
    LLMError,
    TrustedInstruction,
    UntrustedContent,
    Usage,
)

__all__ = [
    "CostQuote",
    "FakeProvider",
    "GenerationRequest",
    "GenerationResponse",
    "InvalidCostError",
    "InvalidRequestError",
    "LLMError",
    "LLMProvider",
    "TrustedInstruction",
    "UnknownProviderError",
    "UntrustedContent",
    "Usage",
    "create_provider",
]
