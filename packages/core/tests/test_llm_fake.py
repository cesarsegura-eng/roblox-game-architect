import pytest

from core.llm import (
    FakeProvider,
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    Message,
    UntrustedBlock,
    get_provider,
)


def _req(text: str = "hello", **kw) -> LLMRequest:
    return LLMRequest(system="sys", messages=(Message("user", text),), **kw)


def test_fake_satisfies_interface() -> None:
    assert isinstance(FakeProvider(), LLMProvider)


def test_default_is_deterministic() -> None:
    a = FakeProvider().complete(_req())
    b = FakeProvider().complete(_req())
    assert a == b
    assert a.usage.cost_usd == 0.0


def test_different_requests_differ() -> None:
    p = FakeProvider()
    assert p.complete(_req("a")).text != p.complete(_req("b")).text


def test_untrusted_block_changes_digest() -> None:
    p = FakeProvider()
    plain = p.complete(_req())
    with_ctx = p.complete(_req(untrusted=(UntrustedBlock("file", "x"),)))
    assert plain.text != with_ctx.text


def test_script_then_rules_then_fallback() -> None:
    p = FakeProvider(script=["one"], rules=[("plan", "PLAN")])
    assert p.complete(_req("plan it")).text == "one"
    assert p.complete(_req("plan it")).text == "PLAN"
    assert p.complete(_req("zzz")).text.startswith("fake-response:")
    assert len(p.calls) == 3


def test_invalid_max_tokens() -> None:
    with pytest.raises(LLMProviderError):
        FakeProvider().complete(_req(max_tokens=0))


def test_factory_defaults_to_fake() -> None:
    assert get_provider(env={}).name == "fake"
    assert get_provider(env={"LLM_PROVIDER": "fake"}).name == "fake"


def test_factory_unknown_provider() -> None:
    with pytest.raises(LLMProviderError):
        get_provider("nope")
