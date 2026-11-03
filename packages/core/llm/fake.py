"""Deterministic, offline, zero-cost provider (ADR-0003, invariant I7).

Same request, same response, on every run and machine: no clock, randomness,
network or environment is read. Canned rules match on the *trusted* channel
only, so untrusted content can never steer the fake's behaviour.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal

from .framing import render_trusted, render_untrusted_channel
from .types import CostQuote, FinishReason, GenerationRequest, GenerationResponse, Usage

FAKE_MODEL = "fake-1"


def _count_tokens(text: str) -> int:
    """Whitespace tokens: crude, but stable and good enough for budget tests."""
    return len(text.split())


class FakeProvider:
    name = "fake"

    def __init__(self, responses: Mapping[str, str] | None = None) -> None:
        """`responses` maps a substring of the trusted instructions to a canned reply.

        The first matching key in insertion order wins. With no match the reply
        is a digest of the whole request, which is deterministic and distinct
        per request.
        """
        self._responses = dict(responses or {})
        self.calls: list[GenerationRequest] = []

    def quote_max_cost(self, request: GenerationRequest) -> CostQuote | None:
        return CostQuote(max_usd=Decimal(0))

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.calls.append(request)
        trusted = render_trusted(request)
        data = render_untrusted_channel(request)
        text = next((reply for key, reply in self._responses.items() if key in trusted), None)
        if text is None:
            canonical = json.dumps([trusted, data], ensure_ascii=True).encode()
            text = f"fake-response:{hashlib.sha256(canonical).hexdigest()[:16]}"

        words = text.split()
        finish: FinishReason = "stop"
        if len(words) > request.max_output_tokens:
            text = " ".join(words[: request.max_output_tokens])
            finish = "length"

        usage = Usage(
            input_tokens=_count_tokens(trusted) + _count_tokens(data),
            output_tokens=_count_tokens(text),
            cost_usd=Decimal(0),
        )
        return GenerationResponse(
            text=text, provider=self.name, model=FAKE_MODEL, usage=usage, finish_reason=finish
        )
