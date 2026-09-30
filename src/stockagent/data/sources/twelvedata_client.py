"""Fetching from Twelve Data, within the free tier's budget.

The free tier allows eight requests a minute. Going over does not fail loudly;
it returns a 429 that, parsed carelessly, looks like a stock with no data. So
the limit is respected before the request rather than discovered after it.

The limiter spaces requests by watching a window rather than sleeping a fixed
amount between them. A fixed sleep wastes the budget when a request itself took
several seconds, and still overruns when several are fast.

Both the clock and the sleep are injected, so the tests assert on the spacing
decisions instead of waiting a real minute to find out.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx

from stockagent.data.models import Bar, CorporateAction, Dividend, Market
from stockagent.data.sources import twelvedata


@dataclass
class RateLimiter:
    """Allows at most `limit` events in any `window` seconds."""

    limit: int = 8
    window: float = 60.0
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], float] = time.monotonic
    # A small margin, because the provider's idea of the minute boundary and
    # ours will not agree to the millisecond.
    margin: float = 0.5
    _events: deque[float] = field(default_factory=deque, init=False)

    def acquire(self) -> float:
        """Wait if needed, then record an event. Returns seconds waited."""
        waited = 0.0
        while True:
            current = self.now()
            while self._events and current - self._events[0] >= self.window:
                self._events.popleft()
            if len(self._events) < self.limit:
                self._events.append(current)
                return waited
            # Wait until the oldest event leaves the window.
            delay = self.window - (current - self._events[0]) + self.margin
            self.sleep(delay)
            waited += delay


@dataclass
class TwelveDataClient:
    api_key: str
    base_url: str = "https://api.twelvedata.com"
    requests_per_minute: int = 8
    timeout_s: float = 30.0
    # Retries for a 429 that slipped through despite the limiter.
    max_retries: int = 3
    transport: httpx.BaseTransport | None = None
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], float] = time.monotonic

    _client: httpx.Client = field(init=False, repr=False)
    limiter: RateLimiter = field(init=False)
    requests_made: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("TWELVEDATA_API_KEY is empty; set it before collecting")
        self._client = httpx.Client(
            base_url=self.base_url, timeout=self.timeout_s, transport=self.transport
        )
        self.limiter = RateLimiter(
            limit=self.requests_per_minute, sleep=self.sleep, now=self.now
        )

    def get(self, path: str, **params: Any) -> dict:
        """One API call, rate limited, retried on a credit shortage."""
        query = {key: value for key, value in params.items() if value is not None}
        query["apikey"] = self.api_key

        for attempt in range(self.max_retries + 1):
            self.limiter.acquire()
            self.requests_made += 1
            response = self._client.get(f"/{path}", params=query)
            payload = response.json()
            try:
                return twelvedata.guard(payload, context=path)
            except twelvedata.RateLimited:
                if attempt == self.max_retries:
                    raise
                # The window the provider is counting is not the one we are.
                # Waiting a whole window is the only reliable reset.
                self.sleep(self.limiter.window)
        raise AssertionError("unreachable")

    # --- the three endpoints the collector needs ---------------------------

    def time_series(
        self,
        ticker: str,
        *,
        start: date,
        end: date,
        market: Market = "US",
        outputsize: int = 5000,
    ) -> list[Bar]:
        """Daily bars in [start, end].

        `end` is passed one day later than asked for, because the provider
        treats `end_date` as exclusive. Doing that here means no caller has to
        remember it.
        """
        payload = self.get(
            "time_series",
            symbol=ticker,
            interval="1day",
            start_date=start.isoformat(),
            end_date=_day_after(end).isoformat(),
            outputsize=outputsize,
        )
        return twelvedata.parse_time_series(payload, ticker=ticker, market=market)

    def dividends(
        self, ticker: str, *, start: date, end: date | None = None, market: Market = "US"
    ) -> list[Dividend]:
        payload = self.get(
            "dividends",
            symbol=ticker,
            start_date=start.isoformat(),
            end_date=_day_after(end).isoformat() if end else None,
        )
        return twelvedata.parse_dividends(payload, ticker=ticker, market=market)

    def splits(
        self, ticker: str, *, start: date, end: date | None = None, market: Market = "US"
    ) -> list[CorporateAction]:
        payload = self.get(
            "splits",
            symbol=ticker,
            start_date=start.isoformat(),
            end_date=_day_after(end).isoformat() if end else None,
        )
        return twelvedata.parse_splits(payload, ticker=ticker, market=market)

    def close(self) -> None:
        self._client.close()


def _day_after(day: date) -> date:
    return day + timedelta(days=1)
