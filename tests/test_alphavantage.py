"""Parsing Alpha Vantage responses, using saved samples of the real thing."""

from datetime import date

import pytest

from stockagent.data.models import Bar
from stockagent.data.sources.alphavantage import (
    AlphaVantageError,
    RateLimited,
    load_json,
    parse_daily_adjusted,
    parse_dividends,
    parse_splits,
)

SAMPLES = "data/samples/alphavantage"


def sample(name: str):
    return load_json(f"{SAMPLES}/{name}.json")


# --- prices -----------------------------------------------------------------


def test_daily_bars_are_parsed_oldest_first():
    bars = parse_daily_adjusted(sample("ibm_daily_adjusted"), ticker="IBM")

    assert len(bars) == 6
    assert [bar.day for bar in bars] == sorted(bar.day for bar in bars)
    assert bars[-1].day == date(2026, 9, 25)


def test_a_bar_carries_its_prices_market_and_source():
    latest = parse_daily_adjusted(sample("ibm_daily_adjusted"), ticker="IBM")[-1]

    assert latest.open == 226.15
    assert latest.high == 228.99
    assert latest.low == 225.19
    assert latest.close == 225.51
    assert latest.adjusted_close == 225.51
    assert latest.volume == 4147449
    # Currency and source travel with every record so nothing downstream has
    # to remember where a number came from.
    assert latest.currency == "USD"
    assert latest.market == "US"
    assert latest.source == "alphavantage"


def test_weekends_are_simply_absent():
    days = {bar.day for bar in parse_daily_adjusted(sample("ibm_daily_adjusted"), ticker="IBM")}
    # 19 and 20 September 2026 are a Saturday and a Sunday.
    assert date(2026, 9, 19) not in days
    assert date(2026, 9, 20) not in days


# --- dividends --------------------------------------------------------------


def test_dividends_are_parsed_with_all_four_dates():
    dividends = parse_dividends(sample("ibm_dividends"), ticker="IBM")
    latest = dividends[-1]

    assert latest.ex_date == date(2026, 8, 10)
    assert latest.amount == 1.69
    assert latest.declared_on == date(2026, 7, 22)
    assert latest.record_date == date(2026, 8, 10)
    assert latest.paid_on == date(2026, 9, 10)
    assert latest.currency == "USD"


def test_dividends_come_back_oldest_first():
    dividends = parse_dividends(sample("ibm_dividends"), ticker="IBM")
    assert [d.ex_date for d in dividends] == sorted(d.ex_date for d in dividends)


@pytest.mark.parametrize("missing", [None, "", "None", "null"])
def test_a_missing_optional_date_becomes_none(missing):
    payload = {
        "symbol": "X",
        "data": [
            {
                "ex_dividend_date": "2026-01-05",
                "declaration_date": missing,
                "record_date": missing,
                "payment_date": missing,
                "amount": "0.25",
            }
        ],
    }
    (dividend,) = parse_dividends(payload, ticker="X")
    assert dividend.declared_on is None
    assert dividend.paid_on is None
    assert dividend.ex_date == date(2026, 1, 5)


def test_a_dividend_with_no_ex_date_is_dropped():
    # It cannot be placed on a timeline, so it cannot take part in a return.
    payload = {"data": [{"ex_dividend_date": "None", "amount": "0.25"}]}
    assert parse_dividends(payload, ticker="X") == []


# --- splits -----------------------------------------------------------------


def test_splits_are_parsed_oldest_first():
    splits = parse_splits(sample("ibm_splits"), ticker="IBM")

    assert [s.effective_date for s in splits] == [date(1999, 5, 27), date(2021, 11, 4)]
    assert splits[0].factor == 2.0
    assert splits[0].kind == "split"


# --- the responses that are not data ---------------------------------------


def test_the_daily_limit_message_raises_rate_limited():
    # This is HTTP 200 with a friendly sentence. Treated as data it would look
    # like a stock that never traded.
    payload = {"Information": "the standard API rate limit is 25 requests per day"}
    with pytest.raises(RateLimited, match="25 requests per day"):
        parse_daily_adjusted(payload, ticker="IBM")


def test_the_older_throttling_note_also_raises():
    with pytest.raises(RateLimited):
        parse_daily_adjusted({"Note": "please slow down"}, ticker="IBM")


def test_an_unknown_symbol_raises():
    payload = {"Error Message": "Invalid API call"}
    with pytest.raises(AlphaVantageError, match="Invalid API call"):
        parse_daily_adjusted(payload, ticker="NOPE")


@pytest.mark.parametrize(
    "parse", [parse_daily_adjusted, parse_dividends, parse_splits]
)
def test_every_parser_checks_for_a_limit_message(parse):
    # One parser that forgets the check is enough to poison the database, so
    # the check is asserted for all of them rather than the one being edited.
    with pytest.raises(RateLimited):
        parse({"Information": "limit reached"}, ticker="IBM")


def test_a_response_with_no_series_raises_rather_than_returning_nothing():
    with pytest.raises(AlphaVantageError, match="no daily series"):
        parse_daily_adjusted({"Meta Data": {}}, ticker="IBM")


def test_a_non_object_response_raises():
    with pytest.raises(AlphaVantageError, match="expected a JSON object"):
        parse_daily_adjusted(["unexpected"], ticker="IBM")


# --- the record's own guards ------------------------------------------------


def test_a_bar_with_high_below_low_is_rejected():
    with pytest.raises(ValueError, match="below low"):
        Bar(
            ticker="X",
            market="US",
            day=date(2026, 1, 5),
            open=10,
            high=9,
            low=11,
            close=10,
            volume=1,
            currency="USD",
            source="test",
        )
