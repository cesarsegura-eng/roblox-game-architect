"""Smoke-test the exact Lute runtime when it is installed in the environment."""

import shutil

import pytest

from sandbox.parser import LuteSyntaxParser, SyntaxCheckResult

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("lute") is None, reason="Lute is not installed"),
]


def test_pinned_lute_parses_valid_and_invalid_source() -> None:
    parser = LuteSyntaxParser()

    assert parser.parse("local value = 1") == SyntaxCheckResult(syntax_valid=True)
    assert parser.parse("local =") == SyntaxCheckResult(syntax_valid=False)
