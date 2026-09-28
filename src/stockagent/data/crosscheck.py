"""Comparing the same days from two price sources.

One source can be wrong and look perfectly reasonable. A bad close sits in the
database, the agent reports it with a citation, the grader marks it correct
against reference code reading the same bad number, and the whole chain agrees
on something false. A second source is the cheapest defence against that.

Three decisions shape this module:

**Relative tolerance, not absolute.** A gap of one naira means nothing on a
five-hundred-naira share and everything on a five-naira one. The threshold has
to scale with the price or it is wrong at one end of the market or the other.

**Only the raw close is compared.** Vendors apply their own conventions when
adjusting for splits and dividends -- which actions count, what rounding,
whether the most recent day is adjusted at all. Comparing adjusted closes
across vendors produces constant disagreement that means nothing about data
quality. The quoted close is the one number both sources should agree on,
because the exchange published it.

**A day only one source has is not a disagreement.** It is a coverage gap, and
it belongs in COVERAGE.md rather than in a quality alarm. Conflating the two
hides both.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from stockagent.data.models import Bar

# Two vendors reporting the same official closing price should agree to within
# rounding. This is deliberately tight: a loose threshold hides exactly the
# errors the comparison exists to catch.
DEFAULT_TOLERANCE = 0.001


@dataclass(frozen=True)
class Disagreement:
    ticker: str
    day: date
    field_name: str
    values: dict[str, float]
    relative_gap: float

    def describe(self) -> str:
        parts = ", ".join(f"{source} {value:g}" for source, value in sorted(self.values.items()))
        return f"{self.ticker} {self.day} {self.field_name}: {parts} ({self.relative_gap:.2%})"


@dataclass
class CrossCheckResult:
    """What the comparison found.

    `agreed` holds the primary source's bars for days both sources confirm.
    That is what should reach the database when a run is being strict.
    """

    agreed: list[Bar] = field(default_factory=list)
    disagreements: list[Disagreement] = field(default_factory=list)
    only_in_primary: list[Bar] = field(default_factory=list)
    only_in_secondary: list[Bar] = field(default_factory=list)

    @property
    def compared(self) -> int:
        return len(self.agreed) + len(self.disagreements)

    @property
    def agreement_rate(self) -> float | None:
        """Share of overlapping days the two sources agreed on.

        None when there was no overlap, which is a different statement from
        zero and should not be reported as one.
        """
        if self.compared == 0:
            return None
        return len(self.agreed) / self.compared

    def summary(self) -> str:
        rate = "no overlap" if self.agreement_rate is None else f"{self.agreement_rate:.2%}"
        return (
            f"{self.compared} days compared, {len(self.disagreements)} disagreed ({rate} agreed); "
            f"{len(self.only_in_primary)} only in primary, "
            f"{len(self.only_in_secondary)} only in secondary"
        )


def relative_gap(left: float, right: float) -> float:
    """Difference between two prices as a fraction of the larger one.

    Dividing by the larger value keeps the result symmetric, so which source
    was passed first cannot change whether a day is flagged.
    """
    if left == right:
        return 0.0
    # Both values being zero is the equality case above, so the larger one is
    # non-zero here and there is nothing to divide by zero. A zero price
    # against a real one comes out as 1.0, a complete disagreement, which is
    # what it is.
    return abs(left - right) / max(abs(left), abs(right))


def cross_check(
    primary: Iterable[Bar],
    secondary: Iterable[Bar],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    fields: Sequence[str] = ("close",),
) -> CrossCheckResult:
    """Compare two sources day by day for one or more securities."""
    by_key_primary = {(bar.ticker, bar.day): bar for bar in primary}
    by_key_secondary = {(bar.ticker, bar.day): bar for bar in secondary}

    result = CrossCheckResult()

    for key in sorted(by_key_primary.keys() | by_key_secondary.keys()):
        left = by_key_primary.get(key)
        right = by_key_secondary.get(key)

        if left is None:
            result.only_in_secondary.append(right)
            continue
        if right is None:
            result.only_in_primary.append(left)
            continue

        found = _compare_fields(left, right, fields=fields, tolerance=tolerance)
        if found:
            result.disagreements.extend(found)
        else:
            result.agreed.append(left)

    return result


def _compare_fields(
    left: Bar, right: Bar, *, fields: Sequence[str], tolerance: float
) -> list[Disagreement]:
    found = []
    for name in fields:
        left_value = getattr(left, name)
        right_value = getattr(right, name)
        if left_value is None or right_value is None:
            continue
        gap = relative_gap(float(left_value), float(right_value))
        if gap > tolerance:
            found.append(
                Disagreement(
                    ticker=left.ticker,
                    day=left.day,
                    field_name=name,
                    values={left.source: float(left_value), right.source: float(right_value)},
                    relative_gap=gap,
                )
            )
    return found
