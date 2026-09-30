"""The Twelve Data client: rate limiting, retries, and date-range handling."""

from datetime import date

import httpx
import pytest

from stockagent.data.sources.twelvedata import RateLimited, TwelveDataError, load_json
from stockagent.data.sources.twelvedata_client import RateLimiter, TwelveDataClient

SERIES = load_json("data/samples/twelvedata/aapl_time_series.json")
SPLITS = load_json("data/samples/twelvedata/aapl_splits.json")
LIMIT_REPLY = load_json("data/samples/twelvedata/error_rate_limited.json")


class FakeClock:
    """A clock that only moves when something sleeps on it."""

    def __init__(self):
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds

    def advance(self, seconds: float) -> None:
        self.t += seconds


# --- the limiter ------------------------------------------------------------


def test_requests_within_the_limit_never_wait():
    clock = FakeClock()
    limiter = RateLimiter(limit=8, window=60.0, sleep=clock.sleep, now=clock.now)

    for _ in range(8):
        assert limiter.acquire() == 0.0
    assert clock.slept == []


def test_the_ninth_request_in_a_minute_waits_for_the_window():
    clock = FakeClock()
    limiter = RateLimiter(limit=8, window=60.0, sleep=clock.sleep, now=clock.now)

    for _ in range(8):
        limiter.acquire()
    waited = limiter.acquire()

    # Just over a full window, since all eight were taken at t=0.
    assert waited == pytest.approx(60.5)


def test_time_spent_on_the_requests_themselves_counts_towards_the_window():
    # A fixed sleep between calls would waste most of the budget here. The
    # window has already passed while the work was happening, so nothing waits.
    clock = FakeClock()
    limiter = RateLimiter(limit=8, window=60.0, sleep=clock.sleep, now=clock.now)

    for _ in range(8):
        limiter.acquire()
        clock.advance(9.0)

    assert limiter.acquire() == 0.0
    assert clock.slept == []


def test_the_limiter_keeps_working_over_several_windows():
    clock = FakeClock()
    limiter = RateLimiter(limit=2, window=10.0, sleep=clock.sleep, now=clock.now)

    for _ in range(7):
        limiter.acquire()

    # Seven requests at two per ten seconds needs three waits.
    assert len(clock.slept) == 3


# --- the client -------------------------------------------------------------


def client_for(handler, **overrides) -> TwelveDataClient:
    clock = FakeClock()
    settings = {
        "api_key": "test-key",
        "transport": httpx.MockTransport(handler),
        "sleep": clock.sleep,
        "now": clock.now,
    }
    settings.update(overrides)
    built = TwelveDataClient(**settings)
    built.clock = clock  # type: ignore[attr-defined]
    return built


def test_an_empty_api_key_is_refused_up_front():
    # Better than 55 identical 401s and a half-filled database.
    with pytest.raises(ValueError, match="TWELVEDATA_API_KEY is empty"):
        TwelveDataClient(api_key="")


def test_the_key_is_sent_and_the_response_parsed():
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=SERIES)

    bars = client_for(handler).time_series("AAPL", start=date(2026, 9, 14), end=date(2026, 9, 28))

    assert seen["apikey"] == "test-key"
    assert seen["symbol"] == "AAPL"
    assert seen["interval"] == "1day"
    assert len(bars) >= 5


def test_the_end_date_is_sent_one_day_later_than_asked():
    # The provider treats end_date as exclusive. Compensating here means no
    # caller can forget, and the last day of a range is never lost.
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=SERIES)

    client_for(handler).time_series("AAPL", start=date(2026, 9, 14), end=date(2026, 9, 28))

    assert seen["start_date"] == "2026-09-14"
    assert seen["end_date"] == "2026-09-29"


def test_splits_come_back_with_the_uninverted_factor():
    def handler(_request):
        return httpx.Response(200, json=SPLITS)

    (split,) = client_for(handler).splits("AAPL", start=date(2015, 1, 1))
    assert split.factor == 4.0


def test_optional_parameters_are_left_out_rather_than_sent_empty():
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=SPLITS)

    client_for(handler).splits("AAPL", start=date(2015, 1, 1))
    assert "end_date" not in seen


def test_a_rate_limit_reply_is_retried_after_waiting_a_window():
    attempts = {"n": 0}

    def handler(_request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(200, json=LIMIT_REPLY)
        return httpx.Response(200, json=SERIES)

    client = client_for(handler)
    bars = client.time_series("AAPL", start=date(2026, 9, 14), end=date(2026, 9, 28))

    assert attempts["n"] == 2
    assert len(bars) >= 5
    # It waited a full window rather than hammering.
    assert 60.0 in client.clock.slept


def test_a_persistent_rate_limit_eventually_raises():
    def handler(_request):
        return httpx.Response(200, json=LIMIT_REPLY)

    client = client_for(handler, max_retries=2)
    with pytest.raises(RateLimited):
        client.time_series("AAPL", start=date(2026, 9, 14), end=date(2026, 9, 28))

    assert client.requests_made == 3


def test_a_bad_key_is_not_retried():
    attempts = {"n": 0}

    def handler(_request):
        attempts["n"] += 1
        return httpx.Response(200, json={"code": 401, "message": "bad key", "status": "error"})

    client = client_for(handler)
    with pytest.raises(TwelveDataError):
        client.time_series("AAPL", start=date(2026, 9, 14), end=date(2026, 9, 28))

    # Retrying a rejected key would burn the whole minute's budget to reach
    # the same error.
    assert attempts["n"] == 1


def test_requests_are_counted_for_the_budget_report():
    def handler(_request):
        return httpx.Response(200, json=SPLITS)

    client = client_for(handler)
    client.splits("AAPL", start=date(2015, 1, 1))
    client.splits("MSFT", start=date(2015, 1, 1))

    assert client.requests_made == 2


def test_a_run_of_calls_is_spaced_to_stay_inside_the_budget():
    def handler(_request):
        return httpx.Response(200, json=SPLITS)

    client = client_for(handler, requests_per_minute=8)
    for _ in range(10):
        client.splits("AAPL", start=date(2015, 1, 1))

    # Ten calls at eight a minute cannot happen without waiting.
    assert client.clock.slept
