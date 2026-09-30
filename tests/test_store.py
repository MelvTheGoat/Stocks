"""The parquet + DuckDB store."""

from datetime import date

import pytest

from stockagent.data.models import Alias, Bar, CorporateAction, Dividend, Security
from stockagent.data.store import MarketStore


def bar(day: int, close: float = 100.0, source: str = "alphavantage", ticker: str = "AAPL") -> Bar:
    return Bar(
        ticker=ticker,
        market="US",
        day=date(2026, 9, day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        currency="USD",
        source=source,
        adjusted_close=close,
    )


@pytest.fixture
def store(tmp_path) -> MarketStore:
    return MarketStore(tmp_path / "db")


# --- writing and reading ----------------------------------------------------


def test_bars_round_trip(store):
    store.write_bars([bar(21), bar(22, 101.5)])

    rows = store.query("SELECT ticker, day, close, currency FROM bars ORDER BY day")
    assert rows == [
        ("AAPL", date(2026, 9, 21), 100.0, "USD"),
        ("AAPL", date(2026, 9, 22), 101.5, "USD"),
    ]


def test_querying_before_anything_is_written_gives_no_rows_not_an_error(store):
    # Every view exists from the start, so code written against the full
    # schema works before the first collection has run.
    assert store.query("SELECT * FROM bars") == []
    assert store.query("SELECT * FROM dividends") == []
    assert store.query("SELECT * FROM aliases") == []


def test_writing_the_same_day_twice_does_not_duplicate_it(store):
    store.write_bars([bar(21)])
    store.write_bars([bar(21)])

    assert store.query("SELECT count(*) FROM bars") == [(1,)]


def test_re_collecting_a_day_replaces_the_stored_price(store):
    store.write_bars([bar(21, close=100.0)])
    store.write_bars([bar(21, close=137.5)])

    assert store.query("SELECT close FROM bars") == [(137.5,)]


def test_the_same_day_from_two_sources_is_kept_twice(store):
    # Source is part of the key on purpose: the cross-check needs both
    # versions of a day to compare them.
    store.write_bars([bar(21, 100.0, source="alphavantage"), bar(21, 100.2, source="stooq")])

    assert store.query("SELECT count(*) FROM bars") == [(2,)]


def test_a_second_write_leaves_earlier_days_alone(store):
    store.write_bars([bar(21), bar(22)])
    store.write_bars([bar(23)])

    days = store.query("SELECT day FROM bars ORDER BY day")
    assert [d for (d,) in days] == [date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)]


def test_the_store_survives_being_reopened(store, tmp_path):
    store.write_bars([bar(21)])

    reopened = MarketStore(tmp_path / "db")
    assert reopened.query("SELECT count(*) FROM bars") == [(1,)]


# --- the other tables -------------------------------------------------------


def test_dividends_round_trip_with_their_optional_dates(store):
    store.write_dividends(
        [
            Dividend(
                ticker="IBM",
                market="US",
                ex_date=date(2026, 8, 10),
                amount=1.69,
                currency="USD",
                source="alphavantage",
                paid_on=date(2026, 9, 10),
            )
        ]
    )

    assert store.query("SELECT amount, paid_on, declared_on FROM dividends") == [
        (1.69, date(2026, 9, 10), None)
    ]


def test_splits_and_bonus_issues_share_one_table(store):
    store.write_actions(
        [
            CorporateAction("AAPL", "US", date(2020, 8, 31), 4.0, "split", "alphavantage"),
            CorporateAction("DANGCEM", "NGX", date(2026, 5, 4), 1.2, "bonus", "ngx-report"),
        ]
    )

    rows = store.query("SELECT ticker, kind, factor FROM actions ORDER BY ticker")
    assert rows == [("AAPL", "split", 4.0), ("DANGCEM", "bonus", 1.2)]


def test_securities_write_their_aliases_to_the_lookup_table(store):
    store.write_securities(
        [
            Security(
                ticker="GTCO",
                market="NGX",
                name="Guaranty Trust Holding Company Plc",
                currency="NGN",
                aliases=(
                    Alias("Guaranty Trust Bank", "name", until=date(2021, 6, 24)),
                    Alias("GUARANTY", "ticker", until=date(2021, 6, 24)),
                ),
            )
        ]
    )

    assert store.query("SELECT count(*) FROM securities") == [(1,)]
    rows = store.query("SELECT text, kind, until FROM aliases ORDER BY text")
    assert rows == [
        ("GUARANTY", "ticker", date(2021, 6, 24)),
        ("Guaranty Trust Bank", "name", date(2021, 6, 24)),
    ]


def test_a_security_with_no_aliases_writes_cleanly(store):
    store.write_securities([Security("AAPL", "US", "Apple Inc.", "USD")])

    assert store.query("SELECT count(*) FROM securities") == [(1,)]
    assert store.query("SELECT count(*) FROM aliases") == [(0,)]


def test_the_two_markets_keep_their_own_currencies(store):
    store.write_bars(
        [
            bar(21, ticker="AAPL"),
            Bar("DANGCEM", "NGX", date(2026, 9, 21), 480, 490, 478, 485, 12, "NGN", "ngx"),
        ]
    )

    rows = store.query("SELECT ticker, currency FROM bars ORDER BY ticker")
    assert rows == [("AAPL", "USD"), ("DANGCEM", "NGN")]


# --- coverage ---------------------------------------------------------------


def test_coverage_reports_the_range_and_count_per_security(store):
    store.write_bars([bar(21), bar(22), bar(23), bar(21, ticker="MSFT")])

    coverage = {row.ticker: row for row in store.coverage()}

    assert coverage["AAPL"].first_day == date(2026, 9, 21)
    assert coverage["AAPL"].last_day == date(2026, 9, 23)
    assert coverage["AAPL"].trading_days == 3
    assert coverage["MSFT"].trading_days == 1


def test_coverage_lists_every_source_a_security_has(store):
    store.write_bars([bar(21, source="alphavantage"), bar(21, 100.1, source="stooq")])

    (row,) = store.coverage()
    assert row.sources == ("alphavantage", "stooq")
    # One calendar day, seen twice. Counting it as two would overstate what we
    # actually cover.
    assert row.trading_days == 1


def test_coverage_of_an_empty_store_is_empty(store):
    assert store.coverage() == []
