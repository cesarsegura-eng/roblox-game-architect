"""Unit tests for SpendBudget and BudgetedLLMProvider (AGENT_MAX_USD_PER_SESSION, ADR-0002)."""

import threading
from decimal import Decimal

import pytest

from core.budget import (
    DEFAULT_MAX_USD_PER_SESSION,
    BudgetedLLMProvider,
    InvalidSpendLimitError,
    ProviderQuoteViolation,
    QuoteUnavailableError,
    Reservation,
    ReservationError,
    SpendBudget,
    SpendBudgetError,
    SpendLimitExceededError,
)
from core.llm import (
    CostQuote,
    FakeProvider,
    GenerationRequest,
    GenerationResponse,
    InvalidCostError,
    LLMProvider,
    TrustedInstruction,
    Usage,
)

D = Decimal
REQ = GenerationRequest(instructions=(TrustedInstruction("hi"),))


class StubProvider:
    """Quotes `quote`, charges `cost`, or raises `error`; counts generate calls."""

    name = "stub"

    def __init__(self, quote="0.30", cost="0.10", error=None, gate=None, entered=None):
        self.quote = None if quote is None else CostQuote(D(quote))
        self.cost = D(cost)
        self.error = error
        self.gate = gate
        self.entered = entered
        self.generate_calls = 0

    def quote_max_cost(self, request):
        return self.quote

    def generate(self, request):
        self.generate_calls += 1
        if self.entered is not None:
            self.entered.set()
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.error is not None:
            raise self.error
        return GenerationResponse("ok", self.name, "m", Usage(1, 1, self.cost))


# types


def test_usage_and_quote_reject_non_decimal_negative_and_non_finite():
    for bad in (0.1, 1, "1", None, D("-0.01"), D("NaN"), D("Infinity"), D("-Infinity")):
        with pytest.raises(InvalidCostError):
            Usage(1, 1, bad)
        with pytest.raises(InvalidCostError):
            CostQuote(bad)
    assert Usage(1, 1).cost_usd == 0
    assert CostQuote(D(0)).max_usd == 0


def test_fake_provider_quotes_exactly_zero_and_is_a_provider():
    fake = FakeProvider()
    assert isinstance(fake, LLMProvider)
    assert fake.quote_max_cost(REQ) == CostQuote(D(0))
    assert fake.generate(REQ).usage.cost_usd == D(0)


# configuration


def test_default_limit_when_variable_absent():
    assert SpendBudget.from_env({}).limit == DEFAULT_MAX_USD_PER_SESSION == D("1.00")


@pytest.mark.parametrize("raw", ["2.50", " 3 ", "0", "0.000", "10.5"])
def test_from_env_accepts_plain_decimals(raw):
    assert SpendBudget.from_env({"AGENT_MAX_USD_PER_SESSION": raw}).limit == D(raw.strip())


@pytest.mark.parametrize(
    "raw", ["", "  ", "abc", "-1", "+1", "1e3", "NaN", "inf", "1,5", "1.", ".5", "1_0", "١٢", "$1"]
)
def test_from_env_present_but_invalid_fails_closed(raw):
    with pytest.raises(InvalidSpendLimitError, match="AGENT_MAX_USD_PER_SESSION"):
        SpendBudget.from_env({"AGENT_MAX_USD_PER_SESSION": raw})


@pytest.mark.parametrize("bad", [1.0, 1, "1", None, D("-1"), D("NaN"), D("Infinity")])
def test_constructor_rejects_invalid_limits(bad):
    with pytest.raises(InvalidSpendLimitError):
        SpendBudget(bad)


# reservation limits


def test_quote_equal_to_remaining_fits_and_one_cent_more_does_not():
    budget = SpendBudget(D("1.00"))
    budget.reserve(CostQuote(D("0.60")))
    with pytest.raises(SpendLimitExceededError):
        budget.reserve(CostQuote(D("0.41")))
    assert budget.reserved == D("0.60")  # the failed reserve changed nothing
    budget.reserve(CostQuote(D("0.40")))
    assert budget.remaining == 0


def test_reserve_without_quote_is_refused():
    with pytest.raises(QuoteUnavailableError):
        SpendBudget(D(5)).reserve(None)


def test_zero_limit_admits_only_zero_quotes():
    budget = SpendBudget(D(0))
    budget.reserve(CostQuote(D(0)))
    with pytest.raises(SpendLimitExceededError):
        budget.reserve(CostQuote(D("0.0001")))


def test_settle_releases_reservation_and_records_actual():
    budget = SpendBudget(D("1.00"))
    r = budget.reserve(CostQuote(D("0.50")))
    budget.settle(r, D("0.20"))
    assert (budget.spent, budget.reserved, budget.remaining) == (D("0.20"), 0, D("0.80"))
    with pytest.raises(ReservationError):
        budget.settle(r, D("0.20"))
    with pytest.raises(ReservationError):
        budget.settle_uncertain(r)
    assert budget.spent == D("0.20")


def test_reservation_from_another_budget_is_rejected():
    r = SpendBudget(D(1)).reserve(CostQuote(D("0.1")))
    with pytest.raises(ReservationError):
        SpendBudget(D(1)).settle(r, D(0))


def test_settle_rejects_invalid_actual_and_keeps_reservation():
    budget = SpendBudget(D(1))
    r = budget.reserve(CostQuote(D("0.5")))
    for bad in (0.1, D("-1"), D("NaN")):
        with pytest.raises(SpendBudgetError):
            budget.settle(r, bad)
    assert budget.reserved == D("0.5")


def test_quote_violation_is_recorded_released_and_raised():
    budget = SpendBudget(D("1.00"))
    r = budget.reserve(CostQuote(D("0.30")))
    with pytest.raises(ProviderQuoteViolation):
        budget.settle(r, D("0.70"))
    assert (budget.spent, budget.reserved) == (D("0.70"), 0)
    with pytest.raises(SpendLimitExceededError):
        budget.reserve(CostQuote(D("0.31")))  # only 0.30 is left


def test_violation_beyond_limit_blocks_all_further_paid_calls():
    budget = SpendBudget(D("1.00"))
    r = budget.reserve(CostQuote(D("0.10")))
    with pytest.raises(ProviderQuoteViolation):
        budget.settle(r, D("5"))
    assert budget.remaining == D("-4.00")
    with pytest.raises(SpendLimitExceededError):
        budget.reserve(CostQuote(D(0)))


def test_arithmetic_is_exact_not_float():
    budget = SpendBudget(D("0.3"))
    for _ in range(3):
        budget.settle(budget.reserve(CostQuote(D("0.1"))), D("0.1"))
    assert budget.spent == D("0.3")
    with pytest.raises(SpendLimitExceededError):
        budget.reserve(CostQuote(D("0.0000000001")))


def test_inexact_arithmetic_fails_closed():
    budget = SpendBudget(D("1E+100"))
    budget.reserve(CostQuote(D("1E-100")))  # exact on its own: reserved is 0 before it
    # limit - reserved needs ~200 digits: inexact, so it must raise, never round.
    with pytest.raises(SpendBudgetError):
        _ = budget.remaining
    with pytest.raises(SpendBudgetError):
        budget.reserve(CostQuote(D("1E-100")))  # a second reservation hits the same sum
    assert budget.reserved == D("1E-100")  # the refused reserve changed nothing


def _budget_with_inexact_settlement():
    """Budget whose spent is 1E+100 and which holds one open 1E-100 reservation.

    Adding the 1E-100 to spent needs ~200 digits, so settling it is inexact.
    """
    budget = SpendBudget(D("2E+100"))
    big = budget.reserve(CostQuote(D("1E+100")))
    budget.settle(big, D("1E+100"))
    return budget, budget.reserve(CostQuote(D("1E-100")))


@pytest.mark.parametrize(
    "settle",
    [lambda b, r: b.settle(r, D("1E-100")), lambda b, r: b.settle_uncertain(r)],
    ids=["settle", "settle_uncertain"],
)
def test_failed_settlement_arithmetic_keeps_the_reservation(settle):
    budget, r = _budget_with_inexact_settlement()
    for _ in range(2):  # still open after the failure, so a retry fails the same way
        with pytest.raises(SpendBudgetError) as err:
            settle(budget, r)
        assert not isinstance(err.value, ReservationError)
        assert (budget.spent, budget.reserved) == (D("1E+100"), D("1E-100"))


def test_reservation_amount_is_immutable():
    budget = SpendBudget(D(1))
    r = budget.reserve(CostQuote(D("0.5")))
    with pytest.raises(AttributeError):
        r.amount = D(0)
    with pytest.raises(AttributeError):
        r._amount = D(0)
    with pytest.raises(AttributeError):
        del r.amount
    assert r.amount == D("0.5")
    budget.settle_uncertain(r)
    assert (budget.spent, budget.reserved) == (D("0.5"), 0)


def test_forged_or_tampered_reservation_cannot_settle():
    budget = SpendBudget(D(1))
    r = budget.reserve(CostQuote(D("0.5")))
    forged = Reservation(budget, D("0.5"))  # never issued by reserve()
    with pytest.raises(ReservationError):
        budget.settle(forged, D("0.1"))
    with pytest.raises(ReservationError):
        budget.settle_uncertain(forged)
    with pytest.raises(ReservationError):
        budget.settle(object(), D("0.1"))
    assert (budget.spent, budget.reserved) == (0, D("0.5"))
    budget.settle(r, D("0.1"))


def test_double_settlement_is_refused_by_the_budget_itself():
    budget = SpendBudget(D(1))
    r = budget.reserve(CostQuote(D("0.5")))
    budget.settle(r, D("0.1"))
    with pytest.raises(ReservationError):
        budget.settle(r, D("0.1"))
    with pytest.raises(ReservationError):
        budget.settle_uncertain(r)
    assert (budget.spent, budget.reserved) == (D("0.1"), 0)


# concurrency


def test_concurrent_reservations_never_overshoot():
    budget = SpendBudget(D("1.00"))
    start = threading.Barrier(20, timeout=5)
    outcomes = []

    def worker():
        start.wait()
        try:
            budget.reserve(CostQuote(D("0.30")))
            outcomes.append(True)
        except SpendLimitExceededError:
            outcomes.append(False)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not any(t.is_alive() for t in threads)
    assert outcomes.count(True) == 3
    assert budget.reserved == D("0.90")


# BudgetedLLMProvider


def test_budgeted_provider_runs_and_records_actual_cost():
    stub = StubProvider(quote="0.30", cost="0.10")
    budget = SpendBudget(D("1.00"))
    wrapped = BudgetedLLMProvider(stub, budget)
    assert isinstance(wrapped, LLMProvider) and wrapped.name == "stub"
    assert wrapped.generate(REQ).text == "ok"
    assert (budget.spent, budget.reserved) == (D("0.10"), 0)


def test_no_quote_rejects_without_calling_generate():
    stub = StubProvider(quote=None)
    budget = SpendBudget(D("1.00"))
    with pytest.raises(QuoteUnavailableError):
        BudgetedLLMProvider(stub, budget).generate(REQ)
    assert stub.generate_calls == 0
    assert (budget.spent, budget.reserved) == (0, 0)


def test_quote_that_does_not_fit_rejects_without_calling_generate():
    stub = StubProvider(quote="1.01")
    with pytest.raises(SpendLimitExceededError):
        BudgetedLLMProvider(stub, SpendBudget(D("1.00"))).generate(REQ)
    assert stub.generate_calls == 0


def test_quote_failure_rejects_without_calling_generate():
    stub = StubProvider()
    stub.quote_max_cost = lambda request: 1 / 0
    with pytest.raises(QuoteUnavailableError):
        BudgetedLLMProvider(stub, SpendBudget(D(1))).generate(REQ)
    assert stub.generate_calls == 0


def test_malformed_quote_object_is_treated_as_missing():
    stub = StubProvider()
    stub.quote_max_cost = lambda request: D("0.1")  # not a CostQuote
    with pytest.raises(QuoteUnavailableError):
        BudgetedLLMProvider(stub, SpendBudget(D(1))).generate(REQ)
    assert stub.generate_calls == 0


def test_failed_call_consumes_the_full_quote():
    stub = StubProvider(quote="0.30", error=TimeoutError("boom"))
    budget = SpendBudget(D("1.00"))
    with pytest.raises(TimeoutError):
        BudgetedLLMProvider(stub, budget).generate(REQ)
    assert (budget.spent, budget.reserved) == (D("0.30"), 0)


def test_interrupt_during_call_also_consumes_the_full_quote():
    stub = StubProvider(quote="0.30", error=KeyboardInterrupt())
    budget = SpendBudget(D("1.00"))
    with pytest.raises(KeyboardInterrupt):
        BudgetedLLMProvider(stub, budget).generate(REQ)
    assert budget.spent == D("0.30")


def test_actual_above_quote_raises_violation_and_records_cost():
    stub = StubProvider(quote="0.30", cost="0.90")
    budget = SpendBudget(D("1.00"))
    with pytest.raises(ProviderQuoteViolation):
        BudgetedLLMProvider(stub, budget).generate(REQ)
    assert (budget.spent, budget.reserved) == (D("0.90"), 0)


def test_unreadable_usage_charges_full_quote():
    stub = StubProvider(quote="0.30")
    stub.generate = lambda request: GenerationResponse("ok", "stub", "m", usage=None)
    budget = SpendBudget(D("1.00"))
    with pytest.raises(SpendBudgetError):
        BudgetedLLMProvider(stub, budget).generate(REQ)
    assert (budget.spent, budget.reserved) == (D("0.30"), 0)


def test_fake_provider_always_fits_even_with_zero_budget():
    budget = SpendBudget(D(0))
    out = BudgetedLLMProvider(FakeProvider(), budget).generate(REQ)
    assert out.usage.cost_usd == 0 and budget.spent == 0


def test_in_flight_reservation_blocks_a_second_call_until_settled():
    gate = threading.Event()
    entered = threading.Event()
    slow = StubProvider(quote="0.60", cost="0.10", gate=gate, entered=entered)
    budget = SpendBudget(D("1.00"))
    t = threading.Thread(target=BudgetedLLMProvider(slow, budget).generate, args=(REQ,))
    t.start()
    try:
        # Set inside generate(), i.e. after the reservation is held.
        assert entered.wait(timeout=5), "first call never reached the provider"
        other = StubProvider(quote="0.60")
        with pytest.raises(SpendLimitExceededError):
            BudgetedLLMProvider(other, budget).generate(REQ)
        assert other.generate_calls == 0
    finally:
        gate.set()
        t.join(timeout=5)
    assert not t.is_alive()
    assert (budget.spent, budget.reserved) == (D("0.10"), 0)
    BudgetedLLMProvider(StubProvider(quote="0.60"), budget).generate(REQ)
