"""Which days a market traded, worked out from the data rather than a list.

Two things need this. The collector has to skip days with no trading. And the
eval has a whole question type about non-trading days, where the right answer
is the last trading day *and a sentence saying so* -- silently answering with
Friday's price when asked about Saturday is wrong even though the number is
right.

Hardcoding a holiday calendar was the obvious approach and it is the wrong
one. Nigerian public holidays include Eid al-Fitr and Eid al-Adha, which move
against the Gregorian calendar and are confirmed only days ahead by
government announcement. A checked-in list would be quietly wrong every year.
The data already knows which days traded, so the data is the calendar.

That leaves one distinction which has to be got right, because collapsing it
is how a database of gaps starts looking like a database of holidays:

* Nothing traded anywhere that day -> the market was closed.
* Other securities traded but this one did not -> our data has a hole.

The first is a fact about the market. The second is a fact about us, and it
belongs in COVERAGE.md.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

Status = Literal[
    "trading",
    "market_closed",
    "missing_data",
    "before_coverage",
    "after_coverage",
]


@dataclass(frozen=True)
class TradingDayAnswer:
    """What happened on the day asked about, and which day to use instead."""

    asked_for: date
    status: Status
    resolved_to: date | None = None

    @property
    def is_usable(self) -> bool:
        return self.resolved_to is not None

    def explain(self) -> str:
        """A sentence the agent can say. The redirect is never silent."""
        if self.status == "trading":
            return f"{self.asked_for} was a trading day."
        if self.status == "market_closed":
            return (
                f"The market was closed on {self.asked_for}. "
                f"The last trading day before it was {self.resolved_to}."
            )
        if self.status == "missing_data":
            return (
                f"The market traded on {self.asked_for}, but there is no data "
                f"for this security on that day."
            )
        if self.status == "before_coverage":
            return f"{self.asked_for} is before the earliest day there is data for."
        return f"{self.asked_for} is after the most recent day there is data for."


class TradingCalendar:
    """Trading days for one market, and per-security coverage within them."""

    def __init__(
        self,
        market_days: Iterable[date],
        days_by_ticker: Mapping[str, Iterable[date]] | None = None,
    ):
        self._days = frozenset(market_days)
        self._sorted = sorted(self._days)
        self._by_ticker = {
            ticker: frozenset(days) for ticker, days in (days_by_ticker or {}).items()
        }

    @classmethod
    def from_store(cls, store, market: str) -> TradingCalendar:
        rows = store.query(
            "SELECT ticker, day FROM bars WHERE market = ? ORDER BY day", [market]
        )
        by_ticker: dict[str, set[date]] = {}
        for ticker, day in rows:
            by_ticker.setdefault(ticker, set()).add(day)
        return cls({day for _, day in rows}, by_ticker)

    @property
    def days(self) -> frozenset[date]:
        return self._days

    @property
    def first(self) -> date | None:
        return self._sorted[0] if self._sorted else None

    @property
    def last(self) -> date | None:
        return self._sorted[-1] if self._sorted else None

    def is_trading_day(self, day: date) -> bool:
        return day in self._days

    def previous_trading_day(self, day: date) -> date | None:
        """The latest trading day on or before `day`."""
        candidates = [d for d in self._sorted if d <= day]
        return candidates[-1] if candidates else None

    def resolve(self, day: date, ticker: str | None = None) -> TradingDayAnswer:
        """Work out which day to answer with, and why."""
        if not self._sorted:
            return TradingDayAnswer(day, "after_coverage")
        if day < self._sorted[0]:
            return TradingDayAnswer(day, "before_coverage")
        # A date past the end is not a weekend to fall back from -- it is a
        # question we cannot answer, and often a date in the future. Falling
        # back here would turn "no data yet" into a confident stale price.
        if day > self._sorted[-1]:
            return TradingDayAnswer(day, "after_coverage")

        if day not in self._days:
            return TradingDayAnswer(day, "market_closed", self.previous_trading_day(day))

        if ticker is not None and ticker in self._by_ticker:
            if day not in self._by_ticker[ticker]:
                return TradingDayAnswer(day, "missing_data")

        return TradingDayAnswer(day, "trading", day)
