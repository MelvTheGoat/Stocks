"""The records every data source is turned into.

Two markets with different conventions have to end up in one database without
losing what makes them different. The rules here:

* Every record carries the market it belongs to and the currency it is in.
  Naira and dollars must never be added together, and the only way to be sure
  is to make the currency impossible to leave out.
* Every record carries the source it came from. When two sources disagree, the
  answer to "which one said what" has to be in the data, not in someone's
  memory of how the pipeline was wired that week.
* A corporate action is a corporate action. A US split and an NGX bonus issue
  both multiply the share count, so they are one record type with a `kind`
  field, and any return calculation that handles one handles the other. Making
  them separate types is how you end up with returns that are right for Apple
  and wrong for Dangote Cement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Market = Literal["US", "NGX"]
Currency = Literal["USD", "NGN"]

# The currency each market trades in. There is exactly one per market here,
# which is a simplification, but a true one for the stocks in scope.
MARKET_CURRENCY: dict[Market, Currency] = {"US": "USD", "NGX": "NGN"}


@dataclass(frozen=True)
class Bar:
    """One trading day for one security.

    `close` is the price as it was quoted on the day. `adjusted_close` is that
    price restated for splits and dividends since, which is what return
    calculations need. Sources differ in whether they give one, the other, or
    both, so `adjusted_close` is optional and code that needs it has to say so.
    """

    ticker: str
    market: Market
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    currency: Currency
    source: str
    adjusted_close: float | None = None

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(f"{self.ticker} on {self.day}: high {self.high} below low {self.low}")
        if self.volume < 0:
            raise ValueError(f"{self.ticker} on {self.day}: negative volume {self.volume}")


@dataclass(frozen=True)
class Dividend:
    """A cash dividend, keyed on its ex-dividend date.

    The ex-dividend date is the one that matters for returns: buy on or after
    it and you do not receive this dividend. The other three dates are kept
    because NGX announcements quote them and a reader may ask.
    """

    ticker: str
    market: Market
    ex_date: date
    amount: float
    currency: Currency
    source: str
    declared_on: date | None = None
    record_date: date | None = None
    paid_on: date | None = None


@dataclass(frozen=True)
class CorporateAction:
    """A split or a bonus issue: anything that changes the share count.

    `factor` is the number of shares held afterwards for each one held before.
    A 2-for-1 split is 2.0. A one-for-five bonus issue is 1.2, because five
    shares become six.
    """

    ticker: str
    market: Market
    effective_date: date
    factor: float
    kind: Literal["split", "bonus"]
    source: str

    def __post_init__(self) -> None:
        if self.factor <= 0:
            raise ValueError(f"{self.ticker} on {self.effective_date}: factor must be positive")


@dataclass(frozen=True)
class Alias:
    """A name or ticker that used to refer to a security.

    Needed because readers ask about companies by the name they remember.
    "Guaranty Trust Bank" has been GTCO since the holding company
    restructure, and a question using the old name is a fair question, not a
    mistake. `until` is when the alias stopped being current, or None if it is
    still in use alongside the canonical form.
    """

    text: str
    kind: Literal["name", "ticker"]
    until: date | None = None


@dataclass(frozen=True)
class Security:
    ticker: str
    market: Market
    name: str
    currency: Currency
    aliases: tuple[Alias, ...] = ()

    def all_names(self) -> tuple[str, ...]:
        return (self.name, *(a.text for a in self.aliases if a.kind == "name"))

    def all_tickers(self) -> tuple[str, ...]:
        return (self.ticker, *(a.text for a in self.aliases if a.kind == "ticker"))
