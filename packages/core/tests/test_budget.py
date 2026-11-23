"""Unit tests for IterationBudget (AGENT_MAX_ITERATIONS, ADR-0002)."""

import pytest

from core.budget import (
    DEFAULT_MAX_ITERATIONS,
    InvalidIterationLimitError,
    IterationBudget,
    IterationLimitExceededError,
)


def test_allows_exactly_the_limit_then_refuses():
    budget = IterationBudget(3)
    assert [budget.consume() for _ in range(3)] == [1, 2, 3]
    with pytest.raises(IterationLimitExceededError, match="limit of 3"):
        budget.consume()


def test_counter_is_observable_and_not_advanced_on_failure():
    budget = IterationBudget(2)
    assert (budget.limit, budget.consumed, budget.remaining) == (2, 0, 2)
    budget.consume()
    assert (budget.consumed, budget.remaining) == (1, 1)
    budget.consume()
    for _ in range(2):
        with pytest.raises(IterationLimitExceededError):
            budget.consume()
    assert (budget.consumed, budget.remaining) == (2, 0)


def test_limit_of_one():
    budget = IterationBudget(1)
    budget.consume()
    with pytest.raises(IterationLimitExceededError):
        budget.consume()


@pytest.mark.parametrize("bad", [0, -1, True, False, 1.0, "5", None, [3]])
def test_invalid_limits_rejected(bad):
    with pytest.raises(InvalidIterationLimitError):
        IterationBudget(bad)


def test_invalid_limit_is_a_value_error():
    with pytest.raises(ValueError, match="positive"):
        IterationBudget(0)


def test_from_env_absent_uses_default():
    budget = IterationBudget.from_env({})
    assert budget.limit == DEFAULT_MAX_ITERATIONS == 10


def test_from_env_reads_value():
    assert IterationBudget.from_env({"AGENT_MAX_ITERATIONS": "25"}).limit == 25
    assert IterationBudget.from_env({"AGENT_MAX_ITERATIONS": " 7 "}).limit == 7


def test_from_env_reads_process_environment(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "4")
    assert IterationBudget.from_env().limit == 4
    monkeypatch.delenv("AGENT_MAX_ITERATIONS")
    assert IterationBudget.from_env().limit == 10


def test_from_env_ignores_process_environment_when_mapping_given(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "4")
    assert IterationBudget.from_env({}).limit == 10


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "0",
        "-3",
        "+5",
        "1.5",
        "1e2",
        "1_0",
        "abc",
        "5 6",
        "\N{ARABIC-INDIC DIGIT FIVE}",
        "0x10",
        "None",
    ],
)
def test_from_env_present_but_invalid_fails_closed(value):
    with pytest.raises(InvalidIterationLimitError, match="AGENT_MAX_ITERATIONS"):
        IterationBudget.from_env({"AGENT_MAX_ITERATIONS": value})
