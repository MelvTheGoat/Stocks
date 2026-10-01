"""Purpose-built tools over the database: resolve, prices, dividends, actions.

These are the "tools designed for the job" arm of Experiment B. The other arm
gives the model raw SQL and sees whether it does better. The comparison is only
fair if these are genuinely good, so each one does the thing a careless caller
would get wrong:

* `resolve` accepts a former name, because readers use the name they remember.
* `prices` says which trading day it actually used when asked about a closed one.
* `actions` explains what the factor means, since a factor alone is ambiguous
  between a split and a consolidation.

Every one of them reports missing data as missing rather than returning an empty
result that reads like a zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from stockagent.data.calendar import TradingCalendar
from stockagent.data.store import MarketStore
from stockagent.eval import reference
from stockagent.tools.base import ToolResult, ToolSpec, require

_DATE = {"type": "string", "description": "a date as YYYY-MM-DD"}
_TICKER = {"type": "string", "description": "the ticker symbol, for example AAPL"}
_MARKET = {
    "type": "string",
    "enum": ["US", "NGX"],
    "description": "which market; defaults to US",
}

MAX_ROWS = 60


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{field} must be a date as YYYY-MM-DD, got {value!r}") from error


@dataclass
class ResolveTool:
    """Company name, former name, or ticker to a ticker."""

    store: MarketStore

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="resolve_security",
            description=(
                "Find the ticker for a company name, a former name, or a ticker. "
                "Use this first whenever a question names a company in words. "
                "Returns 'not found' if nothing matches, which means the database "
                "does not cover that company."
            ),
            parameters={"name": {"type": "string", "description": "a company name or ticker"}},
            required=("name",),
        )

    def run(self, **arguments) -> ToolResult:
        (name,) = require(arguments, "name")
        found = reference.resolve_name(self.store, str(name))
        if not found:
            return ToolResult.failure(
                f"not found: nothing in the database is called {name!r}. "
                "Do not guess a ticker; say the data does not cover it."
            )
        if len(found) > 1:
            return ToolResult.success(
                f"{name!r} matches more than one security: {', '.join(found)}.",
                sources=("securities", "aliases"),
                tickers=found,
            )
        return ToolResult.success(
            f"{name!r} is {found[0]}.", sources=("securities", "aliases"), tickers=found
        )


@dataclass
class PricesTool:
    """Daily prices over a range, or a single day."""

    store: MarketStore

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="get_prices",
            description=(
                "Daily open, high, low and close for a ticker. Give either 'day' for one "
                "date or 'start' and 'end' for a range. If the date asked for was not a "
                "trading day, the reply says which trading day was used instead; repeat "
                "that in your answer. Returns 'no data' rather than a nearby guess when "
                "the date is outside what is held."
            ),
            parameters={
                "ticker": _TICKER,
                "day": _DATE,
                "start": _DATE,
                "end": _DATE,
                "market": _MARKET,
            },
            required=("ticker",),
        )

    def run(self, **arguments) -> ToolResult:
        (ticker,) = require(arguments, "ticker")
        market = arguments.get("market") or "US"
        ticker = str(ticker).upper()

        bars = reference.load_bars(self.store, market, ticker)
        if not bars:
            return ToolResult.failure(
                f"no data: the database holds no prices for {ticker} on the {market} market."
            )

        if arguments.get("day"):
            return self._single_day(market, ticker, _parse_date(arguments["day"], "day"), bars)

        start = _parse_date(arguments["start"], "start") if arguments.get("start") else bars[0].day
        end = _parse_date(arguments["end"], "end") if arguments.get("end") else bars[-1].day
        inside = [bar for bar in bars if start <= bar.day <= end]
        if not inside:
            return ToolResult.failure(
                f"no data: {ticker} has no trading days between {start} and {end}. "
                f"Data runs from {bars[0].day} to {bars[-1].day}."
            )

        currency = inside[0].currency
        # Long ranges are summarised rather than dumped. A hundred rows of prices
        # crowds out the reasoning and costs tokens for no gain; the first and
        # last close are what a return needs.
        if len(inside) > MAX_ROWS:
            lines = [
                f"{ticker} has {len(inside)} trading days between {start} and {end}, "
                f"quoted in {currency}.",
                f"First: {inside[0].day} closed {inside[0].close:.4f}.",
                f"Last: {inside[-1].day} closed {inside[-1].close:.4f}.",
                f"Highest close {max(b.close for b in inside):.4f}, "
                f"lowest {min(b.close for b in inside):.4f}.",
                "Ask for a narrower range to see every day.",
            ]
        else:
            lines = [f"{ticker} daily closes in {currency}:"]
            lines += [
                f"  {bar.day} open {bar.open:.4f} high {bar.high:.4f} "
                f"low {bar.low:.4f} close {bar.close:.4f}"
                for bar in inside
            ]
        return ToolResult.success(
            "\n".join(lines),
            sources=(
                f"bars:{market}:{ticker}:{inside[0].day}",
                f"bars:{market}:{ticker}:{inside[-1].day}",
            ),
            rows=len(inside),
            currency=currency,
        )

    def _single_day(self, market: str, ticker: str, day: date, bars) -> ToolResult:
        calendar = TradingCalendar.from_store(self.store, market)
        answer = calendar.resolve(day, ticker=ticker)
        if not answer.is_usable:
            # The important refusal. Handing back the latest price for a future
            # date is the single most tempting wrong answer in this whole set.
            return ToolResult.failure(f"no data: {answer.explain()}")

        bar = next(b for b in bars if b.day == answer.resolved_to)
        note = "" if answer.status == "trading" else f" {answer.explain()}"
        return ToolResult.success(
            f"{ticker} on {bar.day}: open {bar.open:.4f}, high {bar.high:.4f}, "
            f"low {bar.low:.4f}, close {bar.close:.4f} {bar.currency}, "
            f"volume {bar.volume}.{note}",
            sources=(f"bars:{market}:{ticker}:{bar.day}",),
            resolved_to=bar.day,
            currency=bar.currency,
        )


@dataclass
class DividendsTool:
    store: MarketStore

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="get_dividends",
            description=(
                "Cash dividends for a ticker, by ex-dividend date. Optionally bounded by "
                "'start' and 'end'. A share bought on or after an ex-dividend date does "
                "not receive that dividend. Returns 'no data' when none are recorded, "
                "which is not the same as the company paying nothing."
            ),
            parameters={"ticker": _TICKER, "start": _DATE, "end": _DATE, "market": _MARKET},
            required=("ticker",),
        )

    def run(self, **arguments) -> ToolResult:
        (ticker,) = require(arguments, "ticker")
        market = arguments.get("market") or "US"
        ticker = str(ticker).upper()

        dividends = reference.load_dividends(self.store, market, ticker)
        if not dividends:
            return ToolResult.failure(
                f"no data: no dividend records for {ticker}. This may mean it pays none, "
                "or that none were collected; the database cannot tell you which."
            )

        if arguments.get("start"):
            start = _parse_date(arguments["start"], "start")
            dividends = [d for d in dividends if d.ex_date > start]
        if arguments.get("end"):
            end = _parse_date(arguments["end"], "end")
            dividends = [d for d in dividends if d.ex_date <= end]

        if not dividends:
            return ToolResult.failure(
                f"no data: {ticker} had no ex-dividend dates in that range."
            )

        currency = dividends[0].currency
        total = sum(d.amount for d in dividends)
        lines = [f"{ticker} dividends in {currency}, by ex-dividend date:"]
        lines += [f"  {d.ex_date} {d.amount:.4f}" for d in dividends[:MAX_ROWS]]
        if len(dividends) > MAX_ROWS:
            lines.append(f"  ... {len(dividends) - MAX_ROWS} more")
        lines.append(f"Total over the {len(dividends)} dates shown: {total:.4f} {currency}.")
        return ToolResult.success(
            "\n".join(lines),
            sources=tuple(f"dividends:{market}:{ticker}:{d.ex_date}" for d in dividends[:10]),
            count=len(dividends),
            total=total,
            currency=currency,
        )


@dataclass
class ActionsTool:
    store: MarketStore

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="get_corporate_actions",
            description=(
                "Share splits and bonus issues for a ticker. Always check this before "
                "comparing two prices from different dates: a price quoted before a split "
                "must be divided by the factor to be comparable with a later one. A factor "
                "above one is a split, below one a consolidation."
            ),
            parameters={"ticker": _TICKER, "market": _MARKET},
            required=("ticker",),
        )

    def run(self, **arguments) -> ToolResult:
        (ticker,) = require(arguments, "ticker")
        market = arguments.get("market") or "US"
        ticker = str(ticker).upper()

        actions = reference.load_actions(self.store, market, ticker)
        if not actions:
            return ToolResult.success(
                f"{ticker} has no recorded splits or bonus issues, so prices from "
                "different dates are directly comparable.",
                sources=(f"actions:{market}:{ticker}",),
                count=0,
            )

        lines = [f"{ticker} share-count changes:"]
        for action in actions:
            word = "bonus issue" if action.kind == "bonus" else "split"
            lines.append(
                f"  {action.effective_date} {word}: each share became {action.factor:g}, "
                f"so divide earlier prices by {action.factor:g}"
            )
        return ToolResult.success(
            "\n".join(lines),
            sources=tuple(f"actions:{market}:{ticker}:{a.effective_date}" for a in actions),
            count=len(actions),
        )
