"""Comparing two price sources."""

from datetime import date

import pytest

from stockagent.data.crosscheck import CrossCheckResult, cross_check, relative_gap
from stockagent.data.models import Bar


def bar(day: int, close: float, source: str = "primary", ticker: str = "AAPL", **extra) -> Bar:
    return Bar(
        ticker=ticker,
        market="US",
        day=date(2026, 9, day),
        open=extra.get("open", close),
        high=extra.get("high", close),
        low=extra.get("low", close),
        close=close,
        volume=extra.get("volume", 1000),
        currency="USD",
        source=source,
        adjusted_close=extra.get("adjusted_close"),
    )


# --- the gap measure --------------------------------------------------------


def test_identical_prices_have_no_gap():
    assert relative_gap(100.0, 100.0) == 0.0


def test_the_gap_is_relative_to_the_price():
    # The same absolute difference of 1.0 is huge on a 5 unit share and small
    # on a 500 unit one. An absolute threshold would be wrong at one end.
    assert relative_gap(5.0, 6.0) == pytest.approx(1 / 6)
    assert relative_gap(500.0, 501.0) == pytest.approx(1 / 501)


def test_the_gap_does_not_depend_on_argument_order():
    assert relative_gap(10.0, 11.0) == relative_gap(11.0, 10.0)


def test_one_price_of_zero_is_a_total_disagreement_not_a_crash():
    # A zero close against a real one is 100% apart, and well over any
    # tolerance, so it gets flagged rather than dividing by zero.
    assert relative_gap(0.0, 10.0) == 1.0
    assert cross_check([bar(21, 0.0)], [bar(21, 10.0, "secondary")]).disagreements


# --- the comparison ---------------------------------------------------------


def test_matching_days_agree_and_keep_the_primary_bar():
    result = cross_check([bar(21, 100.00)], [bar(21, 100.00, source="secondary")])

    assert len(result.agreed) == 1
    assert result.agreed[0].source == "primary"
    assert result.disagreements == []


def test_a_small_rounding_difference_is_tolerated():
    result = cross_check([bar(21, 100.00)], [bar(21, 100.02, source="secondary")])
    assert len(result.agreed) == 1


def test_a_real_difference_is_flagged_with_both_values():
    result = cross_check([bar(21, 100.00)], [bar(21, 112.00, source="secondary")])

    assert result.agreed == []
    (found,) = result.disagreements
    assert found.ticker == "AAPL"
    assert found.day == date(2026, 9, 21)
    assert found.values == {"primary": 100.00, "secondary": 112.00}
    assert found.relative_gap == pytest.approx(12 / 112)


def test_a_disagreement_describes_itself_readably():
    result = cross_check([bar(21, 100.0)], [bar(21, 112.0, source="secondary")])
    text = result.disagreements[0].describe()

    assert "AAPL" in text and "2026-09-21" in text
    assert "primary 100" in text and "secondary 112" in text


def test_a_day_only_the_primary_has_is_a_gap_not_a_disagreement():
    result = cross_check([bar(21, 100.0), bar(22, 101.0)], [bar(21, 100.0, source="secondary")])

    assert len(result.agreed) == 1
    assert result.disagreements == []
    assert [b.day for b in result.only_in_primary] == [date(2026, 9, 22)]


def test_a_day_only_the_secondary_has_is_reported_separately():
    result = cross_check(
        [bar(21, 100.0)],
        [bar(21, 100.0, "secondary"), bar(22, 101.0, "secondary")],
    )

    assert [b.day for b in result.only_in_secondary] == [date(2026, 9, 22)]
    assert result.disagreements == []


def test_different_tickers_on_the_same_day_are_not_compared_with_each_other():
    result = cross_check(
        [bar(21, 100.0, ticker="AAPL")],
        [bar(21, 300.0, source="secondary", ticker="MSFT")],
    )

    assert result.disagreements == []
    assert len(result.only_in_primary) == 1
    assert len(result.only_in_secondary) == 1


def test_adjusted_close_is_left_out_of_the_default_comparison():
    # Vendors adjust differently, so comparing adjusted closes would flag
    # almost every day and mean nothing. The quoted close is the number the
    # exchange published and both sources should have it right.
    result = cross_check(
        [bar(21, 100.0, adjusted_close=90.0)],
        [bar(21, 100.0, source="secondary", adjusted_close=70.0)],
    )
    assert len(result.agreed) == 1


def test_extra_fields_can_be_compared_when_asked():
    result = cross_check(
        [bar(21, 100.0, high=110.0)],
        [bar(21, 100.0, source="secondary", high=130.0)],
        fields=("close", "high"),
    )

    assert [d.field_name for d in result.disagreements] == ["high"]


def test_a_missing_value_on_one_side_is_skipped_rather_than_flagged():
    result = cross_check(
        [bar(21, 100.0, adjusted_close=None)],
        [bar(21, 100.0, source="secondary", adjusted_close=98.0)],
        fields=("adjusted_close",),
    )
    assert result.disagreements == []


# --- reporting --------------------------------------------------------------


def test_the_agreement_rate_counts_only_overlapping_days():
    result = cross_check(
        [bar(21, 100.0), bar(22, 101.0), bar(23, 102.0)],
        [bar(21, 100.0, "secondary"), bar(22, 150.0, "secondary")],
    )

    # Two days overlapped, one agreed. The third is a gap and must not be
    # counted as either agreement or disagreement.
    assert result.compared == 2
    assert result.agreement_rate == 0.5
    assert len(result.only_in_primary) == 1


def test_no_overlap_reports_none_rather_than_zero():
    # "We never compared them" and "they never agreed" are different findings
    # and must not look the same in a report.
    result = cross_check([bar(21, 100.0)], [bar(22, 101.0, "secondary")])

    assert result.compared == 0
    assert result.agreement_rate is None
    assert "no overlap" in result.summary()


def test_an_empty_comparison_is_harmless():
    result = cross_check([], [])
    assert result == CrossCheckResult()
    assert result.agreement_rate is None
