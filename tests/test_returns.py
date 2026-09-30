"""Split adjustment and return arithmetic."""

from datetime import date

import pytest

from stockagent.data.models import Bar, CorporateAction, Dividend
from stockagent.data.returns import (
    adjusted_series,
    compute_return,
    cumulative_factor_after,
    dividends_in_window,
    trailing_dividend_yield,
)


def bar(day: date, close: float, ticker: str = "AAPL") -> Bar:
    return Bar(ticker, "US", day, close, close, close, close, 1000, "USD", "test")


def split(day: date, factor: float, kind: str = "split") -> CorporateAction:
    return CorporateAction("AAPL", "US", day, factor, kind, "test")


def dividend(day: date, amount: float) -> Dividend:
    return Dividend("AAPL", "US", day, amount, "USD", "test")


# --- the cumulative factor --------------------------------------------------


def test_no_actions_means_no_adjustment():
    assert cumulative_factor_after(date(2020, 1, 1), []) == 1.0


def test_only_actions_after_the_day_count():
    actions = [split(date(2019, 6, 1), 2.0), split(date(2021, 6, 1), 4.0)]
    # The 2019 split is already reflected in a 2020 price.
    assert cumulative_factor_after(date(2020, 1, 1), actions) == 4.0


def test_an_action_on_the_day_itself_does_not_count():
    # The effective date's own close is already in post-split terms.
    assert cumulative_factor_after(date(2020, 8, 31), [split(date(2020, 8, 31), 4.0)]) == 1.0


def test_several_actions_multiply():
    actions = [split(date(2021, 1, 1), 2.0), split(date(2022, 1, 1), 3.0)]
    assert cumulative_factor_after(date(2020, 1, 1), actions) == 6.0


def test_the_window_can_be_bounded_at_the_top():
    actions = [split(date(2021, 1, 1), 2.0), split(date(2023, 1, 1), 5.0)]
    # Comparing a 2020 price with a 2022 price only needs what happened between.
    assert cumulative_factor_after(date(2020, 1, 1), actions, up_to=date(2022, 1, 1)) == 2.0


# --- the case that makes this necessary -------------------------------------


def test_apples_four_for_one_split_is_not_a_seventy_five_percent_loss():
    # Quoted prices: about 499 before, about 129 after. Nothing happened to
    # anyone's holding. Unadjusted, this looks like a collapse.
    bars = [bar(date(2020, 8, 28), 499.23), bar(date(2020, 9, 1), 134.18)]
    actions = [split(date(2020, 8, 31), 4.0)]

    unadjusted = bars[-1].close / bars[0].close - 1
    assert unadjusted < -0.7

    result = compute_return(bars, actions)
    # 499.23/4 = 124.81 restated, so the real move is a gain of about 7.5%.
    assert result.split_factor_applied == 4.0
    assert result.start_price == pytest.approx(124.8075)
    assert result.price_return == pytest.approx(0.0751, abs=1e-4)


def test_a_bonus_issue_is_adjusted_exactly_like_a_split():
    # A one-for-five NGX bonus issue: five shares become six, factor 1.2.
    bars = [bar(date(2026, 5, 1), 120.0), bar(date(2026, 6, 1), 110.0)]
    actions = [split(date(2026, 5, 15), 1.2, kind="bonus")]

    result = compute_return(bars, actions)
    # 120/1.2 = 100, so 110 is a 10% gain, not an 8% loss.
    assert result.start_price == pytest.approx(100.0)
    assert result.price_return == pytest.approx(0.10)


def test_a_reverse_split_is_handled_too():
    # A one-for-ten consolidation: ten shares become one, so the factor is 0.1,
    # not 10. The factor is always shares held afterwards per share before, for
    # forward and reverse alike, which is why one code path covers both.
    bars = [bar(date(2026, 1, 5), 1.00), bar(date(2026, 3, 5), 9.00)]
    actions = [split(date(2026, 2, 5), 0.1)]

    result = compute_return(bars, actions)
    # 1.00 becomes 10.00 in post-consolidation terms, so 9.00 is a 10% loss.
    assert result.start_price == pytest.approx(10.0)
    assert result.price_return == pytest.approx(-0.10)


def test_the_factor_convention_matches_what_the_parser_produces():
    # The Twelve Data parser reads "1-for-8 reverse split" as 1/8 = 0.125.
    # If that convention and this one ever drift apart, every return spanning a
    # consolidation silently inverts, so they are pinned against each other.
    from stockagent.data.sources.twelvedata import split_factor

    factor = split_factor({"from_factor": 1, "to_factor": 8, "description": "1-for-8 reverse"})
    assert factor == pytest.approx(0.125)

    bars = [bar(date(2026, 1, 5), 1.00), bar(date(2026, 3, 5), 8.00)]
    result = compute_return(bars, [split(date(2026, 2, 5), factor)])
    # 1.00 restates to 8.00, so 8.00 is flat, not a 700% gain.
    assert result.price_return == pytest.approx(0.0)


# --- returns ----------------------------------------------------------------


def test_a_simple_price_return():
    bars = [bar(date(2026, 1, 5), 100.0), bar(date(2026, 6, 5), 125.0)]
    result = compute_return(bars)

    assert result.price_return == pytest.approx(0.25)
    assert result.price_return_percent == pytest.approx(25.0)
    assert result.dividends_collected == 0.0
    assert result.total_return == result.price_return


def test_dividends_lift_the_total_return_above_the_price_return():
    bars = [bar(date(2026, 1, 5), 100.0), bar(date(2026, 12, 5), 110.0)]
    dividends = [dividend(date(2026, 3, 5), 2.0), dividend(date(2026, 9, 5), 2.0)]

    result = compute_return(bars, (), dividends)

    assert result.price_return == pytest.approx(0.10)
    assert result.dividends_collected == pytest.approx(4.0)
    assert result.total_return == pytest.approx(0.14)


def test_a_dividend_on_the_opening_day_is_not_collected():
    # Buying at that day's close means missing that day's ex-dividend.
    bars = [bar(date(2026, 1, 5), 100.0), bar(date(2026, 6, 5), 100.0)]
    result = compute_return(bars, (), [dividend(date(2026, 1, 5), 5.0)])

    assert result.dividends_collected == 0.0


def test_a_dividend_on_the_closing_day_is_collected():
    bars = [bar(date(2026, 1, 5), 100.0), bar(date(2026, 6, 5), 100.0)]
    result = compute_return(bars, (), [dividend(date(2026, 6, 5), 5.0)])

    assert result.dividends_collected == pytest.approx(5.0)


def test_a_dividend_outside_the_window_is_ignored():
    bars = [bar(date(2026, 1, 5), 100.0), bar(date(2026, 6, 5), 100.0)]
    result = compute_return(bars, (), [dividend(date(2025, 6, 5), 5.0)])

    assert result.dividends_collected == 0.0


def test_a_dividend_before_a_split_is_restated_into_post_split_terms():
    # 0.82 paid before a four-for-one split is 0.205 per post-split share.
    # Adding the raw figure would overstate the income fourfold.
    bars = [bar(date(2020, 8, 1), 400.0), bar(date(2020, 12, 1), 120.0)]
    actions = [split(date(2020, 8, 31), 4.0)]
    result = compute_return(bars, actions, [dividend(date(2020, 8, 10), 0.82)])

    assert result.dividends_collected == pytest.approx(0.205)
    # 400/4 = 100 start, so 120 plus 0.205 of income.
    assert result.total_return == pytest.approx(0.20205)


def test_the_window_can_be_narrowed():
    bars = [bar(date(2026, d, 1), price) for d, price in [(1, 100.0), (6, 150.0), (12, 200.0)]]
    result = compute_return(bars, start=date(2026, 1, 1), end=date(2026, 6, 1))

    assert result.end_day == date(2026, 6, 1)
    assert result.price_return == pytest.approx(0.5)


def test_one_trading_day_is_not_a_return():
    # A return needs two prices. Inventing the second is worse than declining.
    assert compute_return([bar(date(2026, 1, 5), 100.0)]) is None


def test_no_trading_days_is_not_a_return():
    assert compute_return([]) is None


def test_a_window_with_nothing_in_it_is_not_a_return():
    bars = [bar(date(2026, 1, 5), 100.0), bar(date(2026, 6, 5), 125.0)]
    assert compute_return(bars, start=date(2027, 1, 1), end=date(2027, 6, 1)) is None


def test_bars_do_not_have_to_arrive_in_order():
    bars = [bar(date(2026, 6, 5), 125.0), bar(date(2026, 1, 5), 100.0)]
    assert compute_return(bars).price_return == pytest.approx(0.25)


# --- the adjusted series ----------------------------------------------------


def test_the_series_is_restated_into_the_final_days_terms():
    bars = [bar(date(2020, 8, 28), 400.0), bar(date(2020, 9, 1), 130.0)]
    series = adjusted_series(bars, [split(date(2020, 8, 31), 4.0)])

    assert series == [(date(2020, 8, 28), 100.0), (date(2020, 9, 1), 130.0)]


def test_an_empty_series_is_empty():
    assert adjusted_series([], []) == []


# --- dividends and yield ----------------------------------------------------


def test_dividends_in_window_excludes_the_opening_day():
    dividends = [dividend(date(2026, 1, 5), 1.0), dividend(date(2026, 3, 5), 2.0)]
    found = dividends_in_window(dividends, date(2026, 1, 5), date(2026, 6, 5))

    assert [d.ex_date for d in found] == [date(2026, 3, 5)]


def test_trailing_yield_is_the_year_of_dividends_over_the_price():
    dividends = [dividend(date(2026, m, 10), 0.25) for m in (1, 4, 7, 10)]
    assert trailing_dividend_yield(20.0, dividends, date(2026, 12, 31)) == pytest.approx(0.05)


def test_dividends_older_than_the_window_are_left_out():
    dividends = [dividend(date(2020, 1, 10), 5.0), dividend(date(2026, 10, 10), 1.0)]
    assert trailing_dividend_yield(20.0, dividends, date(2026, 12, 31)) == pytest.approx(0.05)


def test_no_dividends_gives_no_yield_rather_than_zero():
    # "It pays nothing" and "we do not know" must not look the same.
    assert trailing_dividend_yield(20.0, [], date(2026, 12, 31)) is None


def test_a_zero_price_gives_no_yield_rather_than_dividing_by_zero():
    assert trailing_dividend_yield(0.0, [dividend(date(2026, 1, 1), 1.0)], date(2026, 6, 1)) is None
