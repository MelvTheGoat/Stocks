"""Parsing Twelve Data responses, using saved samples of the real thing."""

from datetime import date

import pytest

from stockagent.data.sources.twelvedata import (
    RateLimited,
    TwelveDataError,
    load_json,
    parse_dividends,
    parse_splits,
    parse_time_series,
    split_factor,
)

SAMPLES = "data/samples/twelvedata"


def sample(name: str):
    return load_json(f"{SAMPLES}/{name}.json")


# --- prices -----------------------------------------------------------------


def test_bars_are_parsed_oldest_first():
    bars = parse_time_series(sample("aapl_time_series"), ticker="AAPL")

    assert len(bars) >= 5
    assert [bar.day for bar in bars] == sorted(bar.day for bar in bars)


def test_a_bar_carries_prices_currency_and_source():
    bars = parse_time_series(sample("aapl_time_series"), ticker="AAPL")
    latest = bars[-1]

    assert latest.day == date(2026, 9, 28)
    assert latest.close == 338.39999
    assert latest.volume == 32820800
    # Currency comes from the response meta, not from an assumption.
    assert latest.currency == "USD"
    assert latest.source == "twelvedata"


def test_the_quoted_close_is_not_passed_off_as_adjusted():
    # This endpoint reports prices as quoted. Claiming they are adjusted would
    # make every split-crossing return silently wrong.
    for bar in parse_time_series(sample("aapl_time_series"), ticker="AAPL"):
        assert bar.adjusted_close is None


def test_end_date_is_exclusive_in_the_captured_sample():
    # The fixture was requested with end_date=2026-09-29 and the newest bar is
    # the 28th. Recorded as a test so nobody "fixes" the collector's range by
    # removing the compensation for it.
    days = [bar.day for bar in parse_time_series(sample("aapl_time_series"), ticker="AAPL")]
    assert date(2026, 9, 29) not in days
    assert date(2026, 9, 28) in days


def test_a_missing_volume_becomes_zero_rather_than_an_error():
    payload = {
        "meta": {"currency": "USD"},
        "values": [{"datetime": "2026-09-21", "open": "1", "high": "2", "low": "1", "close": "2"}],
    }
    (bar,) = parse_time_series(payload, ticker="X")
    assert bar.volume == 0


# --- dividends --------------------------------------------------------------


def test_dividends_are_parsed_oldest_first():
    dividends = parse_dividends(sample("aapl_dividends"), ticker="AAPL")

    assert len(dividends) >= 4
    assert [d.ex_date for d in dividends] == sorted(d.ex_date for d in dividends)
    assert dividends[-1].ex_date == date(2026, 8, 10)
    assert dividends[-1].amount == 0.27
    assert dividends[-1].currency == "USD"


def test_a_dividend_with_no_ex_date_is_dropped():
    payload = {"dividends": [{"amount": 0.25}, {"ex_date": "2026-01-05", "amount": 0.25}]}
    assert len(parse_dividends(payload, ticker="X")) == 1


# --- splits, and the factor that must not be inverted -----------------------


def test_the_apple_split_is_four_not_a_quarter():
    # Apple's 2020 split gave four shares for one. The response also carries
    # ratio 0.25; using that would divide adjusted prices instead of
    # multiplying them, and nothing would raise.
    (split,) = parse_splits(sample("aapl_splits"), ticker="AAPL")

    assert split.effective_date == date(2020, 8, 31)
    assert split.factor == 4.0
    assert split.kind == "split"


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"from_factor": 4, "to_factor": 1, "description": "4-for-1 split"}, 4.0),
        ({"from_factor": 2, "to_factor": 1, "description": "2-for-1 split"}, 2.0),
        ({"from_factor": 3, "to_factor": 2, "description": "3-for-2 split"}, 1.5),
        # A reverse split: eight shares become one, so the factor is below one.
        ({"from_factor": 1, "to_factor": 8, "description": "1-for-8 reverse split"}, 0.125),
        ({"from_factor": 20, "to_factor": 1, "description": "20:1 split"}, 20.0),
    ],
)
def test_factors_are_read_consistently_with_their_description(row, expected):
    assert split_factor(row) == pytest.approx(expected)


def test_a_factor_that_contradicts_its_description_is_refused():
    # The guard that catches a provider changing the meaning of these fields.
    # Silently picking one would corrupt every return across that date.
    with pytest.raises(TwelveDataError, match="disagree with the description"):
        split_factor({"from_factor": 1, "to_factor": 4, "description": "4-for-1 split"})


def test_a_row_with_no_factors_is_refused():
    with pytest.raises(TwelveDataError, match="no usable factors"):
        split_factor({"ratio": 0.25, "description": "4-for-1 split"})


def test_a_zero_factor_is_refused():
    with pytest.raises(TwelveDataError, match="must be positive"):
        split_factor({"from_factor": 0, "to_factor": 1})


def test_a_description_that_cannot_be_read_is_trusted_to_the_factors():
    # No cross-check available, but the numeric fields are unambiguous on
    # their own. Refusing here would drop real splits over wording changes.
    assert split_factor({"from_factor": 4, "to_factor": 1, "description": "stock split"}) == 4.0
    assert split_factor({"from_factor": 4, "to_factor": 1}) == 4.0


# --- the responses that are not data ---------------------------------------


def test_the_rate_limit_reply_raises_rate_limited():
    with pytest.raises(RateLimited, match="API credits"):
        parse_time_series(sample("error_rate_limited"), ticker="AAPL")


def test_a_bad_key_raises_but_not_as_rate_limited():
    # Waiting and retrying would never fix this, so it must not look transient.
    payload = {"code": 401, "message": "apikey parameter is incorrect", "status": "error"}
    with pytest.raises(TwelveDataError) as caught:
        parse_time_series(payload, ticker="AAPL")
    assert not isinstance(caught.value, RateLimited)


@pytest.mark.parametrize("parse", [parse_time_series, parse_dividends, parse_splits])
def test_every_parser_checks_for_an_error_reply(parse):
    with pytest.raises(RateLimited):
        parse(sample("error_rate_limited"), ticker="AAPL")


def test_a_response_with_no_values_raises_rather_than_returning_nothing():
    with pytest.raises(TwelveDataError, match="no values"):
        parse_time_series({"meta": {}}, ticker="AAPL")


def test_a_non_object_response_raises():
    with pytest.raises(TwelveDataError, match="expected a JSON object"):
        parse_time_series([], ticker="AAPL")
