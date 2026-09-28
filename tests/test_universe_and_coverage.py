"""The universe file, and the generated coverage report."""

from datetime import date

import pytest

from stockagent.data.coverage_report import build_coverage_markdown
from stockagent.data.models import Bar
from stockagent.data.store import MarketStore
from stockagent.data.universe import (
    US_UNIVERSE,
    UniverseEntry,
    benchmark,
    companies,
    load_universe,
)

# --- the shipped universe ---------------------------------------------------


def test_the_us_universe_loads():
    entries = load_universe(US_UNIVERSE)
    assert len(entries) >= 50


def test_the_us_universe_has_exactly_one_benchmark():
    entries = load_universe(US_UNIVERSE)
    marks = [entry for entry in entries if entry.is_benchmark]

    assert [entry.ticker for entry in marks] == ["SPY"]
    assert benchmark(entries).ticker == "SPY"
    assert len(companies(entries)) == len(entries) - 1


def test_every_us_entry_has_a_name_and_a_cik():
    # Both come from the SEC file. A blank one means the build script found
    # no match and wrote the row anyway, which it must never do.
    for entry in load_universe(US_UNIVERSE):
        assert entry.name, entry.ticker
        assert entry.cik, entry.ticker
        assert entry.currency == "USD"
        assert entry.market == "US"


def test_the_us_universe_has_no_duplicate_tickers():
    tickers = [entry.ticker for entry in load_universe(US_UNIVERSE)]
    assert len(tickers) == len(set(tickers))


def test_a_universe_entry_converts_to_a_security():
    entry = load_universe(US_UNIVERSE)[0]
    security = entry.to_security()

    assert security.ticker == entry.ticker
    assert security.currency == "USD"


def test_a_universe_with_no_benchmark_returns_none():
    # A market can be collected before a benchmark exists for it. That is a
    # missing capability, not an error.
    assert benchmark([UniverseEntry("AAPL", "US", "Apple Inc.", "USD")]) is None


# --- the coverage report ----------------------------------------------------


def bar(ticker: str, day: int, market: str = "US") -> Bar:
    currency = "USD" if market == "US" else "NGN"
    return Bar(ticker, market, date(2026, 9, day), 10, 10, 10, 10, 1, currency, "alphavantage")


@pytest.fixture
def universe() -> dict[str, list[UniverseEntry]]:
    return {
        "US": [
            UniverseEntry("AAPL", "US", "Apple Inc.", "USD"),
            UniverseEntry("MSFT", "US", "MICROSOFT CORP", "USD"),
            UniverseEntry("SPY", "US", "SPDR S&P 500 ETF TRUST", "USD", role="benchmark"),
        ]
    }


def test_a_collected_security_appears_with_its_range(tmp_path, universe):
    store = MarketStore(tmp_path / "db")
    store.write_bars([bar("AAPL", 21), bar("AAPL", 22)])

    text = build_coverage_markdown(store, universe, generated_on=date(2026, 9, 28))

    assert "| AAPL | Apple Inc. | 2026-09-21 | 2026-09-22 | 2 | alphavantage |" in text


def test_securities_with_no_data_are_named_not_omitted(tmp_path, universe):
    store = MarketStore(tmp_path / "db")
    store.write_bars([bar("AAPL", 21)])

    text = build_coverage_markdown(store, universe, generated_on=date(2026, 9, 28))

    # The whole point of the file. A gap that is not listed is a gap nobody
    # will remember at write-up time.
    assert "No data at all" in text
    assert "- MSFT" in text
    assert "- SPY" in text


def test_an_empty_database_says_so_plainly(tmp_path, universe):
    store = MarketStore(tmp_path / "db")

    text = build_coverage_markdown(store, universe, generated_on=date(2026, 9, 28))

    assert "No price data has been collected for this market yet." in text
    assert "0 with price data" in text


def test_data_outside_the_universe_is_flagged(tmp_path, universe):
    store = MarketStore(tmp_path / "db")
    store.write_bars([bar("AAPL", 21), bar("TSLA", 21)])

    text = build_coverage_markdown(store, universe, generated_on=date(2026, 9, 28))

    assert "In the database but not in the universe" in text
    assert "- TSLA" in text


def test_a_market_with_data_but_no_universe_is_not_hidden(tmp_path, universe):
    store = MarketStore(tmp_path / "db")
    store.write_bars([bar("AAPL", 21), bar("DANGCEM", 21, market="NGX")])

    text = build_coverage_markdown(store, universe, generated_on=date(2026, 9, 28))

    assert "## NGX" in text
    assert "no universe file defines what was meant to be here" in text


def test_the_file_says_when_it_was_generated_and_not_to_edit_it(tmp_path, universe):
    store = MarketStore(tmp_path / "db")

    text = build_coverage_markdown(store, universe, generated_on=date(2026, 9, 28))

    assert "2026-09-28" in text
    assert "Do not edit by hand" in text
