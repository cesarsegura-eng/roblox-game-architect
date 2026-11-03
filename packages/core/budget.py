"""Run bounds for the autonomous loop (ADR-0002): iterations and spend.

`IterationBudget` is the AGENT_MAX_ITERATIONS guard. `SpendBudget` and
`BudgetedLLMProvider` are the AGENT_MAX_USD_PER_SESSION hard cap: a paid call
runs only if its provider gave a maximum-cost quote that fits the remainder.
Neither guard is wired into a loop yet, because the loop does not exist.
"""

from __future__ import annotations

import decimal
import os
import re
import threading
from collections.abc import Mapping
from decimal import Decimal

from .llm.provider import LLMProvider
from .llm.types import CostQuote, GenerationRequest, GenerationResponse

ENV_VAR = "AGENT_MAX_ITERATIONS"
DEFAULT_MAX_ITERATIONS = 10

SPEND_ENV_VAR = "AGENT_MAX_USD_PER_SESSION"
DEFAULT_MAX_USD_PER_SESSION = Decimal("1.00")

_DIGITS = re.compile(r"[0-9]+")
_DECIMAL = re.compile(r"[0-9]+(?:\.[0-9]+)?")

# Exact arithmetic or an error: an inexact (rounded) sum could understate spend.
_CTX = decimal.Context(
    prec=60,
    traps=[decimal.InvalidOperation, decimal.Overflow, decimal.Inexact, decimal.DivisionByZero],
)


class IterationBudgetError(Exception):
    """Base class for iteration-budget failures."""


class InvalidIterationLimitError(IterationBudgetError, ValueError):
    """The configured limit is not a positive integer."""


class IterationLimitExceededError(IterationBudgetError):
    """`consume()` was called with the budget already spent."""


class IterationBudget:
    """Allows exactly `limit` iterations, then refuses the next one."""

    def __init__(self, limit: int) -> None:
        # bool is a subclass of int, so it needs an explicit rejection.
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise InvalidIterationLimitError(
                f"iteration limit must be an int, got {type(limit).__name__}"
            )
        if limit <= 0:
            raise InvalidIterationLimitError(f"iteration limit must be positive, got {limit}")
        self._limit = limit
        self._consumed = 0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> IterationBudget:
        """Build a budget from AGENT_MAX_ITERATIONS.

        Only a variable that is absent falls back to the default of 10. A
        variable that is present but empty, blank or not a plain positive
        integer raises: a mistyped limit must never become a silent default.
        """
        source = os.environ if env is None else env
        if ENV_VAR not in source:
            return cls(DEFAULT_MAX_ITERATIONS)
        raw = source[ENV_VAR]
        text = raw.strip() if isinstance(raw, str) else raw
        # int() would also accept "+5", "1_0" and non-ASCII digits; require ASCII digits only.
        if not isinstance(text, str) or not _DIGITS.fullmatch(text):
            raise InvalidIterationLimitError(f"{ENV_VAR} must be a positive integer, got {raw!r}")
        value = int(text)
        # The constructor would reject 0 too, but its message does not name the variable.
        if value == 0:
            raise InvalidIterationLimitError(f"{ENV_VAR} must be a positive integer, got {raw!r}")
        return cls(value)

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def consumed(self) -> int:
        return self._consumed

    @property
    def remaining(self) -> int:
        return self._limit - self._consumed

    def consume(self) -> int:
        """Spend one iteration and return the count consumed so far.

        Raises before the limit would be exceeded; the counter is not advanced
        on failure.
        """
        if self._consumed >= self._limit:
            raise IterationLimitExceededError(
                f"iteration limit of {self._limit} reached; refusing iteration {self._consumed + 1}"
            )
        self._consumed += 1
        return self._consumed


class SpendBudgetError(Exception):
    """Base class for spend-cap failures."""


class InvalidSpendLimitError(SpendBudgetError, ValueError):
    """The configured spend limit is not a finite, non-negative Decimal."""


class QuoteUnavailableError(SpendBudgetError):
    """No reliable maximum-cost quote exists for the call, so it is refused."""


class SpendLimitExceededError(SpendBudgetError):
    """The quote does not fit in what is left of the budget."""


class ReservationError(SpendBudgetError):
    """A reservation was settled twice or does not belong to this budget."""


class ProviderQuoteViolation(SpendBudgetError):
    """A provider charged more than the maximum it quoted. The actual cost was recorded."""


def _check_money(value: object, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise SpendBudgetError(f"{label} must be a finite, non-negative Decimal, got {value!r}")
    return value


def _add(a: Decimal, b: Decimal) -> Decimal:
    try:
        return _CTX.add(a, b)
    except decimal.DecimalException as exc:
        raise SpendBudgetError(f"cannot add {a} and {b} exactly") from exc


def _sub(a: Decimal, b: Decimal) -> Decimal:
    try:
        return _CTX.subtract(a, b)
    except decimal.DecimalException as exc:
        raise SpendBudgetError(f"cannot subtract {b} from {a} exactly") from exc


class Reservation:
    """A held amount of a `SpendBudget`; settle it exactly once."""

    __slots__ = ("_amount", "_budget")

    def __init__(self, budget: SpendBudget, amount: Decimal) -> None:
        object.__setattr__(self, "_budget", budget)
        object.__setattr__(self, "_amount", amount)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Reservation is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("Reservation is immutable")

    @property
    def amount(self) -> Decimal:
        return self._amount


class SpendBudget:
    """A USD cap for one session, counted as `spent + reserved`.

    A call is admitted by `reserve(quote)` only if the quote fits in
    `limit - spent - reserved`; check and hold happen under one lock, so
    concurrent callers cannot jointly overshoot. Thread-safe.
    """

    def __init__(self, limit: Decimal) -> None:
        if isinstance(limit, Decimal) and limit.is_finite() and limit >= 0:
            self._limit = limit
        else:
            raise InvalidSpendLimitError(
                f"spend limit must be a finite, non-negative Decimal, got {limit!r}"
            )
        self._spent = Decimal(0)
        self._reserved = Decimal(0)
        # The budget, not the Reservation, is the authority on what is still open.
        self._open: set[Reservation] = set()
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> SpendBudget:
        """Build a budget from AGENT_MAX_USD_PER_SESSION (plain decimal, e.g. "2.50").

        Only an absent variable falls back to the default of 1.00 USD. A present
        one that is empty, blank, signed, exponent-form, non-finite or otherwise
        not a plain non-negative decimal raises (fail closed). 0 is valid and
        refuses every call whose quote is above zero.
        """
        source = os.environ if env is None else env
        if SPEND_ENV_VAR not in source:
            return cls(DEFAULT_MAX_USD_PER_SESSION)
        raw = source[SPEND_ENV_VAR]
        text = raw.strip() if isinstance(raw, str) else raw
        if not isinstance(text, str) or not _DECIMAL.fullmatch(text):
            raise InvalidSpendLimitError(
                f"{SPEND_ENV_VAR} must be a non-negative decimal number, got {raw!r}"
            )
        return cls(Decimal(text))

    @property
    def limit(self) -> Decimal:
        return self._limit

    @property
    def spent(self) -> Decimal:
        with self._lock:
            return self._spent

    @property
    def reserved(self) -> Decimal:
        with self._lock:
            return self._reserved

    @property
    def remaining(self) -> Decimal:
        """`limit - spent - reserved`; negative after a quote violation overshoots."""
        with self._lock:
            return self._remaining()

    def _remaining(self) -> Decimal:
        return _sub(_sub(self._limit, self._spent), self._reserved)

    def reserve(self, quote: CostQuote | None) -> Reservation:
        """Hold `quote.max_usd`, or raise without changing any state."""
        if not isinstance(quote, CostQuote):
            raise QuoteUnavailableError("no maximum-cost quote; refusing the paid call")
        with self._lock:
            remaining = self._remaining()
            if quote.max_usd > remaining:
                raise SpendLimitExceededError(
                    f"quote {quote.max_usd} USD exceeds remaining {remaining} USD "
                    f"(limit {self._limit}, spent {self._spent}, reserved {self._reserved})"
                )
            new_reserved = _add(self._reserved, quote.max_usd)
            reservation = Reservation(self, quote.max_usd)
            self._reserved = new_reserved
            self._open.add(reservation)
            return reservation

    def _commit(self, reservation: Reservation, charge: Decimal) -> None:
        """Atomically turn an open reservation into `charge` of spend.

        Caller holds the lock. All arithmetic runs before any state changes: if
        it fails, the reservation stays open and nothing is released uncounted.
        """
        if not isinstance(reservation, Reservation) or reservation not in self._open:
            raise ReservationError("reservation is unknown to this budget or already settled")
        new_reserved = _sub(self._reserved, reservation.amount)
        new_spent = _add(self._spent, charge)
        self._open.remove(reservation)
        self._reserved = new_reserved
        self._spent = new_spent

    def settle(self, reservation: Reservation, actual: Decimal) -> None:
        """Release the reservation and record the real cost.

        If `actual` exceeds the quote, the actual cost is still recorded (and
        the reservation released) and ProviderQuoteViolation is raised. If the
        exact arithmetic fails, the reservation is kept and nothing is recorded.
        """
        _check_money(actual, "actual cost")
        with self._lock:
            self._commit(reservation, actual)
            if actual > reservation.amount:
                raise ProviderQuoteViolation(
                    f"provider charged {actual} USD, above its quoted maximum "
                    f"of {reservation.amount} USD"
                )

    def settle_uncertain(self, reservation: Reservation) -> None:
        """The call failed and may or may not have been billed: charge the full quote.

        Atomic like `settle`: on an arithmetic failure the reservation is kept.
        """
        with self._lock:
            if not isinstance(reservation, Reservation):
                raise ReservationError("reservation is unknown to this budget or already settled")
            self._commit(reservation, reservation.amount)


class BudgetedLLMProvider:
    """Wraps a provider so every call is quoted, reserved, then settled.

    `provider.generate` is never reached without a quote that fits.
    """

    def __init__(self, provider: LLMProvider, budget: SpendBudget) -> None:
        self._provider = provider
        self._budget = budget
        self.name = provider.name

    @property
    def budget(self) -> SpendBudget:
        return self._budget

    def quote_max_cost(self, request: GenerationRequest) -> CostQuote | None:
        return self._provider.quote_max_cost(request)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        try:
            quote = self._provider.quote_max_cost(request)
        except Exception as exc:
            raise QuoteUnavailableError(f"quoting the call failed: {exc!r}") from exc
        reservation = self._budget.reserve(quote)
        try:
            response = self._provider.generate(request)
        except BaseException:
            # The request may have reached the vendor; assume the worst.
            self._budget.settle_uncertain(reservation)
            raise
        try:
            actual = response.usage.cost_usd
            _check_money(actual, "usage.cost_usd")
        except (AttributeError, SpendBudgetError):
            self._budget.settle_uncertain(reservation)
            raise SpendBudgetError(
                "provider response has no valid usage.cost_usd; charged the full quote"
            ) from None
        self._budget.settle(reservation, actual)
        return response
