"""Provider selection by configuration, never by an import in agent code."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .fake import FakeProvider
from .provider import LLMProvider
from .types import LLMError


class UnknownProviderError(LLMError):
    """`LLM_PROVIDER` names a provider that is not registered."""


def create_provider(name: str | None = None, env: Mapping[str, str] | None = None) -> LLMProvider:
    """Build the provider called `name`.

    Without an explicit `name`, read LLM_PROVIDER from `env` (default: the
    process environment), falling back to `fake` when it is unset or blank.
    Pass `env` to avoid touching the global environment, e.g. in tests.

    The optional Anthropic adapter is constructed only when explicitly selected.
    """
    if name is None:
        source = os.environ if env is None else env
        name = source.get("LLM_PROVIDER", "").strip() or "fake"
    if name == "fake":
        return FakeProvider()
    if name == "anthropic":
        from .anthropic import AnthropicProvider

        return AnthropicProvider(env=env)
    raise UnknownProviderError(f"unknown LLM provider {name!r}; available: 'fake', 'anthropic'")
