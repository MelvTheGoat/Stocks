"""Split adjustment and return calculation.

This is the arithmetic every return question depends on, so it is written once,
here, and tested hard. The provider gives prices as quoted, which means the
adjustment is ours to do.

The rule is that a price is comparable with a later price only after being
divided by every share-count change that happened in between. Apple traded near
500 dollars in August 2020 and near 125 the day after its four-for-one split.
Nothing happened to the value of anyone's holding. A return calculation that
misses the split reports a 75% collapse.

Two subtleties that are easy to get wrong:

**Dividends need adjusting too.** A dividend of 82 cents paid before a
four-for-one split is 20.5 cents in post-split terms. Adding the unadjusted
figure to an adjusted price series overstates the income by the split factor.

**Bonus issues are splits.** An NGX one-for-five bonus issue multiplies the
share count by 1.2 exactly as a split would, so both are handled by the same
code path. Treating them separately is how returns come out right for Apple and
wrong for Dangote Cement.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from stockagent.data.models import Bar, CorporateAction, Dividend


@dataclass(frozen=True)
class ReturnResult:
    """A return, with the figures it was worked out from.

    The inputs travel with the answer because an agent citing a return has to
    be able to show where it came from, and because a disagreement with the
    reference implementation is much easier to diagnose from the parts than
    from the total.
    """

    start_day: date
    end_day: date
    start_price: float
    end_price: float
    dividends_collected: float
    split_factor_applied: float
    price_return: float
    total_return: float

    @property
    def price_return_percent(self) -> float:
        return self.price_return * 100

    @property
    def total_return_percent(self) -> float:
        return self.total_return * 100


def cumulative_factor_after(
    day: date, actions: Iterable[CorporateAction], *, up_to: date | None = None
) -> float:
    """Product of every share-count change strictly after `day`.

    `up_to` bounds the window, so a price can be restated into the terms of a
    chosen later date rather than always into today's terms. Comparing two
    prices only needs the changes between them.
    """
    factor = 1.0
    for action in actions:
        if action.effective_date <= day:
            continue
        if up_to is not None and action.effective_date > up_to:
            continue
        factor *= action.factor
    return factor


def adjust_price(
    price: float, day: date, actions: Iterable[CorporateAction], *, up_to: date | None = None
) -> float:
    """Restate a price into the share terms in force at `up_to`."""
    return price / cumulative_factor_after(day, actions, up_to=up_to)


def adjusted_series(
    bars: Sequence[Bar], actions: Sequence[CorporateAction]
) -> list[tuple[date, float]]:
    """The closing prices, all restated into the terms of the final bar."""
    if not bars:
        return []
    last_day = bars[-1].day
    return [(bar.day, adjust_price(bar.close, bar.day, actions, up_to=last_day)) for bar in bars]


def compute_return(
    bars: Sequence[Bar],
    actions: Sequence[CorporateAction] = (),
    dividends: Sequence[Dividend] = (),
    *,
    start: date | None = None,
    end: date | None = None,
) -> ReturnResult | None:
    """Return over a window, split-adjusted, with and without dividends.

    Returns None when the window holds fewer than two trading days, because a
    return needs two prices and inventing one is worse than saying so.

    The window is inclusive and uses the trading days actually present. A caller
    asking about a Saturday should resolve that to a trading day first; see
    `TradingCalendar`.
    """
    inside = [
        bar
        for bar in sorted(bars, key=lambda b: b.day)
        if (start is None or bar.day >= start) and (end is None or bar.day <= end)
    ]
    if len(inside) < 2:
        return None

    first, last = inside[0], inside[-1]

    # Everything is restated into the share terms in force on the last day, so
    # the two prices are directly comparable.
    factor = cumulative_factor_after(first.day, actions, up_to=last.day)
    start_price = first.close / factor
    end_price = last.close

    # A dividend counts if its ex-date falls after the opening day and on or
    # before the closing day: buying at the first close means owning the share
    # through every ex-date after it.
    collected = 0.0
    for dividend in dividends:
        if first.day < dividend.ex_date <= last.day:
            collected += adjust_price(dividend.amount, dividend.ex_date, actions, up_to=last.day)

    price_return = end_price / start_price - 1
    total_return = (end_price + collected) / start_price - 1

    return ReturnResult(
        start_day=first.day,
        end_day=last.day,
        start_price=start_price,
        end_price=end_price,
        dividends_collected=collected,
        split_factor_applied=factor,
        price_return=price_return,
        total_return=total_return,
    )


def dividends_in_window(
    dividends: Iterable[Dividend], start: date, end: date
) -> list[Dividend]:
    """Dividends with an ex-date in (start, end]."""
    return sorted(
        (d for d in dividends if start < d.ex_date <= end), key=lambda d: d.ex_date
    )


def trailing_dividend_yield(
    price: float, dividends: Iterable[Dividend], as_of: date, *, months: int = 12
) -> float | None:
    """Dividends over the past `months`, as a fraction of the current price.

    None when the price is zero or there are no dividends in the window: a
    yield of zero and an unknown yield are different statements, and reporting
    one as the other is the kind of thing this project exists not to do.
    """
    if price <= 0:
        return None
    # Approximate the window in days rather than pulling in a calendar library
    # for one subtraction; the eval's questions are about a trailing year.
    days = int(months * 30.44)
    window_start = date.fromordinal(as_of.toordinal() - days)
    paid = [d.amount for d in dividends if window_start < d.ex_date <= as_of]
    if not paid:
        return None
    return sum(paid) / price
