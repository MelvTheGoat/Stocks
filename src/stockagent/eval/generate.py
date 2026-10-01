"""Builds the question set from whatever the database actually holds.

Questions are generated rather than written by hand because there need to be
enough of them to measure a few points of difference, and because a generator
cannot get bored and start writing only the easy ones.

Two rules keep the set honest:

**Generation is seeded.** The same database and the same seed give the same
questions, so a version is reproducible and a result can be traced back to the
exact wording that produced it.

**Every generated question is checked against the reference code before it is
kept.** A question the reference cannot answer is not a hard question, it is a
broken one, and leaving it in would drag every score down by a fixed amount that
nobody could account for. The intentionally unanswerable cases are hand-written
and live in `cases.py`, so anything unanswerable here is a mistake.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from stockagent.data.calendar import TradingCalendar
from stockagent.data.store import MarketStore
from stockagent.eval import reference
from stockagent.eval.cases import DELIBERATE_KINDS, all_cases
from stockagent.eval.schema import Params, Question

# How many of each data-driven kind to generate. Chosen so no single kind
# dominates the headline number: a set that is 80% price lookups reports mostly
# how good the agent is at price lookups.
DEFAULT_COUNTS = {
    "price_on_date": 30,
    "non_trading_day": 15,
    "return_over_period": 30,
    "adjusted_return": 15,
    "compare_two": 20,
    "best_in_group": 12,
    "worst_in_group": 8,
    "dividend_amount": 15,
    "dividend_yield": 15,
    "vs_benchmark": 20,
    "name_to_ticker": 15,
}


@dataclass
class GenerationReport:
    kept: list[Question]
    dropped: dict[str, str]

    def summary(self) -> str:
        return f"{len(self.kept)} questions kept, {len(self.dropped)} dropped"


def _tickers_with_data(store: MarketStore, market: str) -> list[str]:
    rows = store.query(
        "SELECT DISTINCT ticker FROM bars WHERE market = ? ORDER BY ticker", [market]
    )
    return [ticker for (ticker,) in rows]


def _tickers_with_dividends(store: MarketStore, market: str) -> list[str]:
    rows = store.query(
        "SELECT DISTINCT ticker FROM dividends WHERE market = ? ORDER BY ticker", [market]
    )
    return [ticker for (ticker,) in rows]


def _names(store: MarketStore, market: str) -> list[tuple[str, str]]:
    rows = store.query(
        "SELECT name, ticker FROM securities WHERE market = ? ORDER BY ticker", [market]
    )
    aliases = store.query(
        """
        SELECT a.text, a.ticker FROM aliases a
        WHERE a.market = ? AND a.kind = 'name' ORDER BY a.ticker
        """,
        [market],
    )
    return [(name, ticker) for name, ticker in rows] + [
        (name, ticker) for name, ticker in aliases
    ]


def _pick_window(
    rng: random.Random, days: Sequence[date], *, minimum: int = 20
) -> tuple[date, date] | None:
    """A window with at least `minimum` trading days in it."""
    if len(days) <= minimum:
        return None
    start_index = rng.randrange(0, len(days) - minimum)
    end_index = rng.randrange(start_index + minimum, len(days))
    return days[start_index], days[end_index]


def generate(
    store: MarketStore,
    *,
    as_of: date,
    market: str = "US",
    benchmark: str = "SPY",
    seed: int = 0,
    counts: dict[str, int] | None = None,
) -> GenerationReport:
    """Generate the data-driven questions, keeping only answerable ones."""
    rng = random.Random(seed)
    counts = {**DEFAULT_COUNTS, **(counts or {})}

    tickers = [t for t in _tickers_with_data(store, market) if t != benchmark]
    if not tickers:
        return GenerationReport(kept=[], dropped={"all": f"no price data for {market}"})

    calendar = TradingCalendar.from_store(store, market)
    days = sorted(calendar.days)
    paying = [t for t in _tickers_with_dividends(store, market) if t != benchmark]
    named = _names(store, market)

    proposed: list[Question] = []

    def add(kind: str, index: int, text: str, params: Params) -> None:
        proposed.append(
            Question(
                id=f"{market.lower()}-{kind.replace('_', '-')}-{index:04d}",
                kind=kind,
                market=market,
                text=text,
                as_of=as_of,
                params=params,
            )
        )

    for index in range(counts["price_on_date"]):
        ticker = rng.choice(tickers)
        day = rng.choice(days)
        add(
            "price_on_date",
            index,
            f"What did {ticker} close at on {day.isoformat()}?",
            Params(tickers=(ticker,), day=day),
        )

    # Deliberately aimed at weekends, where the right answer uses the previous
    # trading day and says which one it used.
    for index in range(counts["non_trading_day"]):
        ticker = rng.choice(tickers)
        trading_day = rng.choice(days[1:])
        closed = trading_day + timedelta(days=1)
        while calendar.is_trading_day(closed):
            closed += timedelta(days=1)
        if closed > days[-1]:
            continue
        add(
            "non_trading_day",
            index,
            f"What did {ticker} close at on {closed.isoformat()}?",
            Params(tickers=(ticker,), day=closed),
        )

    for index in range(counts["return_over_period"]):
        window = _pick_window(rng, days)
        if window is None:
            break
        start, end = window
        ticker = rng.choice(tickers)
        add(
            "return_over_period",
            index,
            f"What was {ticker}'s price return from {start.isoformat()} to {end.isoformat()}?",
            Params(tickers=(ticker,), start=start, end=end),
        )

    for index in range(counts["adjusted_return"]):
        window = _pick_window(rng, days)
        if window is None:
            break
        start, end = window
        ticker = rng.choice(paying or tickers)
        add(
            "adjusted_return",
            index,
            f"What was {ticker}'s total return including dividends from "
            f"{start.isoformat()} to {end.isoformat()}?",
            Params(tickers=(ticker,), start=start, end=end),
        )

    for index in range(counts["compare_two"]):
        window = _pick_window(rng, days)
        if window is None or len(tickers) < 2:
            break
        start, end = window
        pair = tuple(rng.sample(tickers, 2))
        add(
            "compare_two",
            index,
            f"Which did better between {start.isoformat()} and {end.isoformat()}, "
            f"{pair[0]} or {pair[1]}?",
            Params(tickers=pair, start=start, end=end),
        )

    for kind, best in (("best_in_group", True), ("worst_in_group", False)):
        word = "best" if best else "worst"
        for index in range(counts[kind]):
            window = _pick_window(rng, days)
            if window is None or len(tickers) < 4:
                break
            start, end = window
            group = tuple(rng.sample(tickers, min(5, len(tickers))))
            add(
                kind,
                index,
                f"Which of {', '.join(group)} performed {word} between "
                f"{start.isoformat()} and {end.isoformat()}?",
                Params(tickers=group, start=start, end=end),
            )

    for index in range(counts["dividend_amount"]):
        if not paying:
            break
        window = _pick_window(rng, days, minimum=120)
        if window is None:
            break
        start, end = window
        ticker = rng.choice(paying)
        add(
            "dividend_amount",
            index,
            f"How much did {ticker} pay per share in dividends between "
            f"{start.isoformat()} and {end.isoformat()}?",
            Params(tickers=(ticker,), start=start, end=end),
        )

    for index in range(counts["dividend_yield"]):
        if not paying:
            break
        ticker = rng.choice(paying)
        day = rng.choice(days[len(days) // 2 :])
        add(
            "dividend_yield",
            index,
            f"What was {ticker}'s trailing twelve-month dividend yield on {day.isoformat()}?",
            Params(tickers=(ticker,), day=day, months=12),
        )

    if benchmark in _tickers_with_data(store, market):
        for index in range(counts["vs_benchmark"]):
            window = _pick_window(rng, days)
            if window is None:
                break
            start, end = window
            ticker = rng.choice(tickers)
            add(
                "vs_benchmark",
                index,
                f"Did {ticker} beat {benchmark} between {start.isoformat()} "
                f"and {end.isoformat()}?",
                Params(tickers=(ticker,), name=benchmark, start=start, end=end),
            )

    for index, (name, _ticker) in enumerate(named[: counts["name_to_ticker"]]):
        add(
            "name_to_ticker",
            index,
            f"What ticker does {name} trade under?",
            Params(name=name),
        )

    return _keep_answerable(store, proposed)


def _keep_answerable(store: MarketStore, proposed: Sequence[Question]) -> GenerationReport:
    """Drop anything the reference code cannot answer, and say why.

    A question that cannot be scored is not a hard question. Keeping it would
    subtract a constant from every result, and nobody looking at the number
    later would know it was there.
    """
    kept: list[Question] = []
    dropped: dict[str, str] = {}
    for question in proposed:
        try:
            truth = reference.answer(store, question)
        except reference.ReferenceError as error:
            dropped[question.id] = f"malformed: {error}"
            continue
        if not truth.is_answerable:
            dropped[question.id] = f"unanswerable: {truth.explanation}"
            continue
        kept.append(question)
    return GenerationReport(kept=kept, dropped=dropped)


def build_question_set(
    store: MarketStore,
    *,
    as_of: date,
    market: str = "US",
    benchmark: str = "SPY",
    seed: int = 0,
) -> GenerationReport:
    """The data-driven questions plus the hand-written robustness cases."""
    report = generate(store, as_of=as_of, market=market, benchmark=benchmark, seed=seed)

    calendar = TradingCalendar.from_store(store, market)
    written = all_cases(as_of, market, data_end=calendar.last)

    # The advice, injection and unanswerable cases are kept unchecked: their
    # correct answer is a refusal, so the reference reporting "unanswerable" is
    # the expected outcome rather than a problem.
    report.kept.extend(q for q in written if q.kind in DELIBERATE_KINDS)

    # The Pidgin cases ask about real figures, so they go through the same filter
    # as the generated ones. A Pidgin question the data cannot answer is not a
    # test of phrasing; it is a mislabelled unanswerable case, and it would be
    # scored against the wrong expectation.
    checkable = _keep_answerable(store, [q for q in written if q.kind not in DELIBERATE_KINDS])
    report.kept.extend(checkable.kept)
    report.dropped.update(checkable.dropped)
    return report
