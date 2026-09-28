"""Trading days derived from the data."""

from datetime import date

import pytest

from stockagent.data.calendar import TradingCalendar
from stockagent.data.models import Bar
from stockagent.data.store import MarketStore

# Friday 18th through Friday 25th September 2026, with the weekend missing.
WEEK = [date(2026, 9, d) for d in (18, 21, 22, 23, 24, 25)]
SATURDAY = date(2026, 9, 19)
SUNDAY = date(2026, 9, 20)


@pytest.fixture
def calendar() -> TradingCalendar:
    return TradingCalendar(WEEK)


def test_a_trading_day_is_recognised(calendar):
    assert calendar.is_trading_day(date(2026, 9, 21))
    assert not calendar.is_trading_day(SATURDAY)


def test_the_range_is_reported(calendar):
    assert calendar.first == date(2026, 9, 18)
    assert calendar.last == date(2026, 9, 25)


def test_resolving_a_trading_day_returns_that_day(calendar):
    answer = calendar.resolve(date(2026, 9, 21))

    assert answer.status == "trading"
    assert answer.resolved_to == date(2026, 9, 21)


@pytest.mark.parametrize("closed", [SATURDAY, SUNDAY])
def test_a_closed_day_falls_back_to_the_friday(calendar, closed):
    answer = calendar.resolve(closed)

    assert answer.status == "market_closed"
    assert answer.resolved_to == date(2026, 9, 18)


def test_the_fallback_is_explained_not_silent(calendar):
    # Answering a Saturday question with Friday's price and saying nothing is
    # wrong even though the number is right.
    text = calendar.resolve(SATURDAY).explain()

    assert "closed on 2026-09-19" in text
    assert "last trading day before it was 2026-09-18" in text


def test_a_date_after_the_data_does_not_fall_back(calendar):
    # This is the future-date case. Falling back to the last trading day
    # would turn "there is no data yet" into a confident stale price.
    answer = calendar.resolve(date(2027, 1, 4))

    assert answer.status == "after_coverage"
    assert answer.resolved_to is None
    assert answer.is_usable is False


def test_a_date_before_the_data_is_reported_as_such(calendar):
    answer = calendar.resolve(date(2019, 1, 2))

    assert answer.status == "before_coverage"
    assert answer.resolved_to is None


def test_an_empty_calendar_answers_nothing():
    answer = TradingCalendar([]).resolve(date(2026, 9, 21))

    assert answer.is_usable is False
    assert TradingCalendar([]).first is None


def test_previous_trading_day_of_a_trading_day_is_itself(calendar):
    assert calendar.previous_trading_day(date(2026, 9, 21)) == date(2026, 9, 21)


def test_previous_trading_day_before_all_data_is_none(calendar):
    assert calendar.previous_trading_day(date(2019, 1, 1)) is None


# --- the distinction that matters ------------------------------------------


def test_a_hole_in_one_security_is_not_a_market_holiday():
    # The market traded: other securities have bars. This one does not, which
    # is a fact about our collection, not about the exchange.
    calendar = TradingCalendar(WEEK, {"AAPL": WEEK, "MSFT": [d for d in WEEK if d.day != 22]})

    answer = calendar.resolve(date(2026, 9, 22), ticker="MSFT")

    assert answer.status == "missing_data"
    assert answer.resolved_to is None
    assert "no data for this security" in answer.explain()


def test_a_security_with_full_coverage_resolves_normally():
    calendar = TradingCalendar(WEEK, {"AAPL": WEEK})
    assert calendar.resolve(date(2026, 9, 22), ticker="AAPL").status == "trading"


def test_a_weekend_is_still_a_holiday_even_when_a_ticker_is_named():
    calendar = TradingCalendar(WEEK, {"AAPL": WEEK})
    assert calendar.resolve(SATURDAY, ticker="AAPL").status == "market_closed"


def test_an_unknown_ticker_falls_back_to_the_market_view():
    calendar = TradingCalendar(WEEK, {"AAPL": WEEK})
    assert calendar.resolve(date(2026, 9, 22), ticker="NOPE").status == "trading"


# --- built from the store ---------------------------------------------------


def bar(day: date, ticker: str, market: str = "US") -> Bar:
    return Bar(ticker, market, day, 10, 10, 10, 10, 1, "USD", "test")


def test_the_calendar_can_be_read_out_of_the_store(tmp_path):
    store = MarketStore(tmp_path / "db")
    store.write_bars([bar(day, "AAPL") for day in WEEK] + [bar(WEEK[0], "MSFT")])

    calendar = TradingCalendar.from_store(store, "US")

    assert calendar.days == frozenset(WEEK)
    assert calendar.resolve(WEEK[1], ticker="MSFT").status == "missing_data"
    assert calendar.resolve(WEEK[1], ticker="AAPL").status == "trading"


def test_each_market_gets_its_own_calendar(tmp_path):
    # The NGX and the NYSE close on different days. One shared calendar would
    # report a Nigerian public holiday as missing US data.
    store = MarketStore(tmp_path / "db")
    store.write_bars(
        [bar(date(2026, 10, 1), "DANGCEM", market="NGX"), bar(date(2026, 10, 2), "AAPL")]
    )

    assert TradingCalendar.from_store(store, "US").days == {date(2026, 10, 2)}
    assert TradingCalendar.from_store(store, "NGX").days == {date(2026, 10, 1)}
