"""Deterministic, offline, zero-cost provider (ADR-0003). The default.

Same request in, same response out, on every machine and every run. Responses
come from, in order:

1. a scripted queue, consumed one per call (`FakeProvider(script=[...])`);
2. the first matching rule, as `(substring, response)` checked against the last
   user message;
3. a stable echo derived from a hash of the request.

A green suite against this class is not proof the system works live; it only
proves the engine's logic is sound given well-formed model output.
"""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Iterable

from core.llm.base import LLMProviderError, LLMRequest, LLMResponse, Usage

FAKE_MODEL = "fake-1"


def _digest(request: LLMRequest) -> str:
    h = hashlib.sha256()
    for part in (request.system, *(f"{m.role}:{m.content}" for m in request.messages)):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    for block in request.untrusted:
        h.update(f"{block.label}:{block.content}".encode())
        h.update(b"\x00")
    return h.hexdigest()


def _tokens(text: str) -> int:
    # Whitespace word count: crude but deterministic and good enough for budgets.
    return len(text.split())


class FakeProvider:
    name = "fake"

    def __init__(
        self,
        script: Iterable[str] = (),
        rules: Iterable[tuple[str, str]] = (),
    ) -> None:
        self._script = deque(script)
        self._rules = tuple(rules)
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        if request.max_tokens <= 0:
            raise LLMProviderError("max_tokens must be positive")
        self.calls.append(request)
        text = self._respond(request)
        usage = Usage(
            input_tokens=_tokens(request.system) + sum(_tokens(m.content) for m in request.messages),
            output_tokens=_tokens(text),
            cost_usd=0.0,
        )
        return LLMResponse(text=text, model=FAKE_MODEL, usage=usage)

    def _respond(self, request: LLMRequest) -> str:
        if self._script:
            return self._script.popleft()
        last_user = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
        for needle, response in self._rules:
            if needle in last_user:
                return response
        return f"fake-response:{_digest(request)[:16]}"
