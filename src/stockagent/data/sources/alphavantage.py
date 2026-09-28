"""Alpha Vantage: daily prices, dividends and splits for US stocks.

Parsing is kept separate from fetching. Every function here takes an
already-decoded JSON object, so the tests run against saved sample responses
with no network and no API key.

The part that needs care is not the happy path. Alpha Vantage answers a
rate-limited or rejected request with HTTP 200 and a JSON object containing a
polite message instead of data. Handled carelessly, that parses as "this stock
had no trading days", which is indistinguishable from a real gap once it is in
the database. Every entry point checks for those messages first and raises.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from stockagent.data.models import Bar, CorporateAction, Currency, Dividend, Market

SOURCE = "alphavantage"

# Keys Alpha Vantage uses to say "not data". "Information" is the current
# free-tier daily-limit message, "Note" the older throttling one, and
# "Error Message" an unknown symbol or a malformed request.
_LIMIT_KEYS = ("Information", "Note")
_ERROR_KEYS = ("Error Message",)


class AlphaVantageError(Exception):
    """The response was not data."""


class RateLimited(AlphaVantageError):
    """The free tier's request limit was reached.

    Worth separating from other errors: a collector should stop for the day
    rather than treat this as a permanent failure for the symbol.
    """


def guard(payload: Any, *, context: str = "") -> dict:
    """Raise unless the payload actually contains data."""
    where = f" for {context}" if context else ""
    if not isinstance(payload, dict):
        raise AlphaVantageError(f"expected a JSON object{where}, got {type(payload).__name__}")
    for key in _LIMIT_KEYS:
        if key in payload:
            raise RateLimited(f"{key}{where}: {payload[key]}")
    for key in _ERROR_KEYS:
        if key in payload:
            raise AlphaVantageError(f"{key}{where}: {payload[key]}")
    return payload


def _optional_date(value: Any) -> date | None:
    # Alpha Vantage writes a missing date as the string "None", and sometimes
    # as an empty string.
    if value in (None, "", "None", "null"):
        return None
    return date.fromisoformat(str(value))


def parse_daily_adjusted(
    payload: Any,
    *,
    ticker: str,
    market: Market = "US",
    currency: Currency = "USD",
) -> list[Bar]:
    """Parse a TIME_SERIES_DAILY_ADJUSTED response into bars, oldest first."""
    body = guard(payload, context=f"{ticker} daily")
    series = body.get("Time Series (Daily)")
    if not isinstance(series, dict):
        raise AlphaVantageError(f"no daily series for {ticker}; keys were {sorted(body)}")

    bars = [
        Bar(
            ticker=ticker,
            market=market,
            day=date.fromisoformat(day),
            open=float(row["1. open"]),
            high=float(row["2. high"]),
            low=float(row["3. low"]),
            close=float(row["4. close"]),
            adjusted_close=float(row["5. adjusted close"]),
            volume=int(row["6. volume"]),
            currency=currency,
            source=SOURCE,
        )
        for day, row in series.items()
    ]
    return sorted(bars, key=lambda bar: bar.day)


def parse_dividends(
    payload: Any,
    *,
    ticker: str,
    market: Market = "US",
    currency: Currency = "USD",
) -> list[Dividend]:
    """Parse a DIVIDENDS response, oldest first."""
    body = guard(payload, context=f"{ticker} dividends")
    rows = body.get("data")
    if not isinstance(rows, list):
        raise AlphaVantageError(f"no dividend data for {ticker}; keys were {sorted(body)}")

    dividends = []
    for row in rows:
        ex_date = _optional_date(row.get("ex_dividend_date"))
        if ex_date is None:
            # Without an ex-date the record cannot be placed on a timeline, so
            # it cannot be used in a return calculation. Dropping it is right;
            # keeping it dateless would let it be silently miscounted later.
            continue
        dividends.append(
            Dividend(
                ticker=ticker,
                market=market,
                ex_date=ex_date,
                amount=float(row["amount"]),
                currency=currency,
                source=SOURCE,
                declared_on=_optional_date(row.get("declaration_date")),
                record_date=_optional_date(row.get("record_date")),
                paid_on=_optional_date(row.get("payment_date")),
            )
        )
    return sorted(dividends, key=lambda d: d.ex_date)


def parse_splits(
    payload: Any,
    *,
    ticker: str,
    market: Market = "US",
) -> list[CorporateAction]:
    """Parse a SPLITS response, oldest first."""
    body = guard(payload, context=f"{ticker} splits")
    rows = body.get("data")
    if not isinstance(rows, list):
        raise AlphaVantageError(f"no split data for {ticker}; keys were {sorted(body)}")

    return sorted(
        (
            CorporateAction(
                ticker=ticker,
                market=market,
                effective_date=date.fromisoformat(row["effective_date"]),
                factor=float(row["split_factor"]),
                kind="split",
                source=SOURCE,
            )
            for row in rows
        ),
        key=lambda action: action.effective_date,
    )


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())
