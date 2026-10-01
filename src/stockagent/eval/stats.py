"""Confidence intervals and agreement, written out rather than imported.

Two numbers in this project are easy to report misleadingly, so both are computed
here with the caveats attached.

**A confidence interval on an accuracy.** "62% versus 58%" means nothing on a
hundred questions: the interval on each is about plus or minus ten points, so the
difference is noise. Bootstrapping is used rather than a normal approximation
because it behaves sensibly near zero and one, where a lot of these rates sit --
an injection suite scoring 100% would otherwise get an interval extending above
one, which is not a thing.

**Agreement between the LLM judge and a human.** Raw agreement flatters a judge
badly whenever one answer dominates. If 90% of free-text answers are correct, a
judge that says "correct" every single time agrees 90% of the time and is
worthless. Cohen's kappa subtracts the agreement you would get by chance, and it
is the number that decides whether the judge can be trusted.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_RESAMPLES = 2000
DEFAULT_CONFIDENCE = 0.95


@dataclass(frozen=True)
class Interval:
    point: float
    low: float
    high: float
    n: int

    def as_percent(self) -> str:
        if self.n == 0:
            return "no data"
        return f"{self.point * 100:.1f}% ({self.low * 100:.1f}-{self.high * 100:.1f})"

    @property
    def width(self) -> float:
        return self.high - self.low

    def overlaps(self, other: Interval) -> bool:
        """True when the two intervals overlap.

        Not a significance test, but the right first question to ask of two
        results: if the intervals overlap, the difference is not established.
        """
        return self.low <= other.high and other.low <= self.high


def proportion(successes: Sequence[bool] | Sequence[int]) -> float:
    values = list(successes)
    if not values:
        return 0.0
    return sum(1 for value in values if value) / len(values)


def bootstrap_interval(
    outcomes: Sequence[bool] | Sequence[int],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int = 0,
) -> Interval:
    """A confidence interval on a proportion, by resampling.

    Seeded, so the interval reported in the write-up is the interval anyone
    re-running the analysis will get.
    """
    values = [bool(value) for value in outcomes]
    count = len(values)
    if count == 0:
        return Interval(point=0.0, low=0.0, high=0.0, n=0)

    point = proportion(values)
    if count == 1:
        # One observation carries no information about spread, and pretending
        # otherwise with a zero-width interval would be worse than saying so.
        return Interval(point=point, low=0.0, high=1.0, n=1)

    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        sample = [values[rng.randrange(count)] for _ in range(count)]
        means.append(sum(1 for value in sample if value) / count)
    means.sort()

    tail = (1 - confidence) / 2
    low = means[max(0, int(tail * resamples) - 1)]
    high = means[min(resamples - 1, int((1 - tail) * resamples))]
    return Interval(point=point, low=low, high=high, n=count)


@dataclass(frozen=True)
class Agreement:
    """How well two raters agree, and whether that is better than chance."""

    observed: float
    expected: float
    kappa: float
    n: int

    def verdict(self) -> str:
        """A plain reading of the kappa, with the usual rough bands named."""
        if self.n == 0:
            return "no labels to compare"
        if self.kappa >= 0.8:
            band = "strong agreement"
        elif self.kappa >= 0.6:
            band = "substantial agreement"
        elif self.kappa >= 0.4:
            band = "moderate agreement, treat the judge with caution"
        elif self.kappa >= 0.2:
            band = "weak agreement, the judge is not trustworthy yet"
        else:
            band = "little better than chance, do not use this judge"
        return (
            f"{self.observed:.1%} raw agreement, kappa {self.kappa:.2f} "
            f"over {self.n} labels: {band}"
        )

    @property
    def trustworthy(self) -> bool:
        """Whether the judge may be used for reported numbers.

        The bar is deliberately a decision rather than a suggestion. A judge
        below it is not used, because a measurement nobody trusts is worse than
        no measurement at all -- it still gets quoted.
        """
        return self.n >= 30 and self.kappa >= 0.6


def cohens_kappa(mine: Sequence, theirs: Sequence) -> Agreement:
    """Agreement between two raters over the same items, corrected for chance."""
    if len(mine) != len(theirs):
        raise ValueError(f"both raters must label the same items: {len(mine)} vs {len(theirs)}")
    count = len(mine)
    if count == 0:
        return Agreement(observed=0.0, expected=0.0, kappa=0.0, n=0)

    labels = sorted({*map(str, mine), *map(str, theirs)})
    left = [str(value) for value in mine]
    right = [str(value) for value in theirs]

    observed = sum(1 for a, b in zip(left, right, strict=True) if a == b) / count

    # Chance agreement: how often they would match if each kept their own habits
    # but answered independently.
    expected = 0.0
    for label in labels:
        expected += (left.count(label) / count) * (right.count(label) / count)

    if expected >= 1.0:
        # Both raters used one label for everything. They agree completely and
        # the comparison carries no information; kappa is undefined, and
        # reporting 1.0 would be a lie about how much was learned.
        return Agreement(observed=observed, expected=expected, kappa=0.0, n=count)

    kappa = (observed - expected) / (1 - expected)
    return Agreement(observed=observed, expected=expected, kappa=kappa, n=count)


def percentile(values: Sequence[float], fraction: float) -> float:
    """A percentile by nearest rank. Used for latency, where p95 is reported."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = max(0, min(len(ordered) - 1, round(fraction * (len(ordered) - 1))))
    return ordered[position]


def median(values: Sequence[float]) -> float:
    return percentile(values, 0.5)
