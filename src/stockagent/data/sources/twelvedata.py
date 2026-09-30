"""Twelve Data: daily prices, dividends and splits.

Parsing is separate from fetching, so the tests run against saved sample
responses with no network and no API key.

Three things about this provider need care, and all three are the kind of
mistake that produces confident wrong numbers rather than an error:

**The split factor is ambiguous in the response.** A 4-for-1 split arrives as
`{"ratio": 0.25, "from_factor": 4, "to_factor": 1, "description": "4-for-1
split"}`. Reading `ratio` as the factor inverts every split-adjusted return,
and nothing would fail -- the returns would simply be wrong by a factor of
sixteen for Apple. So the factor is taken as `from_factor / to_factor`, and
then checked against the number written in the description. If they disagree,
parsing fails rather than guessing.

**`end_date` is exclusive.** A request for 14th to 29th September returns
nothing dated the 29th. Off by one at the end of a range is silent and would
show up much later as a stock that mysteriously stops a day early.

**There is no adjusted close.** The time series gives the prices as quoted.
Adjusting for splits and dividends is therefore our own job, computed from the
actions and dividends tables. That is more work but it is also the honest
arrangement: the eval asks questions about split-adjusted returns, so the
adjustment is part of what is being tested and should not be a vendor's
undocumented convention.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from stockagent.data.models import Bar, CorporateAction, Currency, Dividend, Market

SOURCE = "twelvedata"

# "4-for-1 split", "1-for-8 reverse split"
_DESCRIPTION = re.compile(r"(\d+(?:\.\d+)?)\s*[-: ]?for[-: ]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

# Tolerance when checking the description against the numeric factors. Wide
# enough for a rounded description, far too tight to let an inversion pass.
_FACTOR_TOLERANCE = 0.01


class TwelveDataError(Exception):
    """The response was not data."""


class RateLimited(TwelveDataError):
    """The per-minute credit limit was reached. Wait, do not give up."""


def guard(payload: Any, *, context: str = "") -> dict:
    """Raise unless the payload contains data."""
    where = f" for {context}" if context else ""
    if not isinstance(payload, dict):
        raise TwelveDataError(f"expected a JSON object{where}, got {type(payload).__name__}")
    if payload.get("status") == "error" or "code" in payload:
        code = payload.get("code")
        message = str(payload.get("message", "no message"))
        if code == 429:
            raise RateLimited(f"{code}{where}: {message}")
        raise TwelveDataError(f"{code}{where}: {message}")
    return payload


def parse_time_series(
    payload: Any,
    *,
    ticker: str,
    market: Market = "US",
    currency: Currency | None = None,
) -> list[Bar]:
    """Parse a time_series response into bars, oldest first.

    `adjusted_close` is left unset: this endpoint reports prices as quoted.
    """
    body = guard(payload, context=f"{ticker} time_series")
    values = body.get("values")
    if not isinstance(values, list):
        raise TwelveDataError(f"no values for {ticker}; keys were {sorted(body)}")

    resolved = currency or body.get("meta", {}).get("currency") or "USD"

    bars = [
        Bar(
            ticker=ticker,
            market=market,
            day=date.fromisoformat(row["datetime"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            # Volume is absent on some days for some instruments.
            volume=int(float(row.get("volume") or 0)),
            currency=resolved,
            source=SOURCE,
        )
        for row in values
    ]
    return sorted(bars, key=lambda bar: bar.day)


def parse_dividends(
    payload: Any,
    *,
    ticker: str,
    market: Market = "US",
    currency: Currency | None = None,
) -> list[Dividend]:
    """Parse a dividends response, oldest first."""
    body = guard(payload, context=f"{ticker} dividends")
    rows = body.get("dividends")
    if not isinstance(rows, list):
        raise TwelveDataError(f"no dividends for {ticker}; keys were {sorted(body)}")

    resolved = currency or body.get("meta", {}).get("currency") or "USD"

    return sorted(
        (
            Dividend(
                ticker=ticker,
                market=market,
                ex_date=date.fromisoformat(row["ex_date"]),
                amount=float(row["amount"]),
                currency=resolved,
                source=SOURCE,
            )
            for row in rows
            if row.get("ex_date")
        ),
        key=lambda dividend: dividend.ex_date,
    )


def split_factor(row: dict) -> float:
    """Shares held afterwards for each one held before.

    A 4-for-1 split returns 4.0. The response also carries `ratio`, which is
    the reciprocal; using it by mistake would invert every adjusted return
    without raising anything, so the factor derived from `from_factor` and
    `to_factor` is verified against the description before being accepted.
    """
    try:
        from_factor = float(row["from_factor"])
        to_factor = float(row["to_factor"])
    except (KeyError, TypeError, ValueError) as error:
        raise TwelveDataError(f"split row has no usable factors: {row}") from error

    if from_factor <= 0 or to_factor <= 0:
        raise TwelveDataError(f"split factors must be positive: {row}")

    factor = from_factor / to_factor

    described = _DESCRIPTION.search(str(row.get("description", "")))
    if described:
        left, right = float(described.group(1)), float(described.group(2))
        if right <= 0:
            raise TwelveDataError(f"split description has a zero divisor: {row}")
        if abs(left / right - factor) > _FACTOR_TOLERANCE:
            raise TwelveDataError(
                f"split factors disagree with the description: "
                f"{from_factor}/{to_factor} = {factor:g} but "
                f"{row.get('description')!r} means {left / right:g}"
            )
    return factor


def parse_splits(
    payload: Any,
    *,
    ticker: str,
    market: Market = "US",
) -> list[CorporateAction]:
    """Parse a splits response, oldest first."""
    body = guard(payload, context=f"{ticker} splits")
    rows = body.get("splits")
    if not isinstance(rows, list):
        raise TwelveDataError(f"no splits for {ticker}; keys were {sorted(body)}")

    return sorted(
        (
            CorporateAction(
                ticker=ticker,
                market=market,
                effective_date=date.fromisoformat(row["date"]),
                factor=split_factor(row),
                kind="split",
                source=SOURCE,
            )
            for row in rows
            if row.get("date")
        ),
        key=lambda action: action.effective_date,
    )


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())
