"""Provider selection by configuration, never by an import in agent code."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from core.llm.base import LLMProvider, LLMProviderError
from core.llm.fake import FakeProvider

DEFAULT_PROVIDER = "fake"

# Real adapters register here when they exist (one thin module each).
_REGISTRY: dict[str, Callable[[], LLMProvider]] = {"fake": FakeProvider}


def get_provider(name: str | None = None, env: Mapping[str, str] | None = None) -> LLMProvider:
    """Return the provider named `name`, else `LLM_PROVIDER`, else the fake."""
    if name is None:
        name = (env if env is not None else os.environ).get("LLM_PROVIDER") or DEFAULT_PROVIDER
    try:
        return _REGISTRY[name]()
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise LLMProviderError(f"unknown LLM provider {name!r}; known: {known}") from None
