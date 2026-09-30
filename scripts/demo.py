"""Runs every piece built so far and prints what it did.

Nothing here reaches the network or a model. It works entirely from the sample
responses saved in `data/samples/`, so it produces the same output on any
machine, and it needs no API key.

Run: python scripts/demo.py
"""

from __future__ import annotations

import dataclasses
import sys
import tempfile
from datetime import date
from pathlib import Path

from stockagent.data.calendar import TradingCalendar
from stockagent.data.coverage_report import build_coverage_markdown
from stockagent.data.crosscheck import cross_check
from stockagent.data.sources.alphavantage import (
    RateLimited,
    load_json,
    parse_daily_adjusted,
    parse_dividends,
    parse_splits,
)
from stockagent.data.store import MarketStore
from stockagent.data.universe import US_UNIVERSE, benchmark, load_universe

SAMPLES = Path("data/samples/alphavantage")


def heading(number: int, text: str) -> None:
    print(f"\n{'=' * 70}\n {number}. {text}\n{'=' * 70}")


def main() -> int:
    heading(1, "Read real saved responses from Alpha Vantage")

    bars = parse_daily_adjusted(load_json(SAMPLES / "ibm_daily_adjusted.json"), ticker="IBM")
    dividends = parse_dividends(load_json(SAMPLES / "ibm_dividends.json"), ticker="IBM")
    splits = parse_splits(load_json(SAMPLES / "ibm_splits.json"), ticker="IBM")

    print(f"{len(bars)} trading days, {len(dividends)} dividends, {len(splits)} splits")
    print(f"\nlatest day parsed:\n  {bars[-1]}")
    print("\nEvery record carries its market, its currency and where it came from,")
    print("so nothing downstream has to remember which source a number is from.")

    heading(2, "A rate-limited reply is not mistaken for an empty stock")

    print("Alpha Vantage answers a throttled request with HTTP 200 and a sentence.")
    print("Read carelessly it looks like a company that never traded.\n")
    try:
        parse_daily_adjusted(
            {"Information": "the standard API rate limit is 25 requests per day"}, ticker="IBM"
        )
    except RateLimited as error:
        print(f"  raised {type(error).__name__}: {error}")

    with tempfile.TemporaryDirectory() as temporary:
        store = MarketStore(Path(temporary) / "db")

        heading(3, "Store it and query it with SQL")

        store.write_bars(bars)
        store.write_dividends(dividends)
        store.write_actions(splits)

        rows = store.query(
            "SELECT day, close, volume FROM bars ORDER BY day DESC LIMIT 3"
        )
        print("  SELECT day, close, volume FROM bars ORDER BY day DESC LIMIT 3\n")
        for day, close, volume in rows:
            print(f"    {day}   {close:>8.2f}   {volume:>12,}")

        total = store.query("SELECT count(*), round(sum(amount), 2) FROM dividends")[0]
        print(f"\n  {total[0]} dividends on record, {total[1]} per share in total")

        heading(4, "Collect the same days again; nothing is duplicated")

        before = store.query("SELECT count(*) FROM bars")[0][0]
        store.write_bars(bars)
        store.write_bars(bars)
        after = store.query("SELECT count(*) FROM bars")[0][0]

        print(f"  rows after one write:    {before}")
        print(f"  rows after three writes: {after}")
        print("\nWrites merge on the record's key. A Kaggle session killed halfway")
        print("through and restarted leaves the database as one clean run would.")

        heading(5, "Catch a bad price by comparing two sources")

        # Same days from a pretend second source, with one close altered.
        second = [dataclasses.replace(bar, source="other-source") for bar in bars]
        second[2] = dataclasses.replace(second[2], close=second[2].close * 1.08)

        result = cross_check(bars, second)
        print(f"  {result.summary()}\n")
        for found in result.disagreements:
            print(f"  flagged: {found.describe()}")
        print("\nThe threshold is relative, not absolute: one naira of difference")
        print("means nothing on a 500 naira share and everything on a 5 naira one.")

        heading(6, "Answer questions about days the market was shut")

        calendar = TradingCalendar.from_store(store, "US")
        for asked in [date(2026, 9, 25), date(2026, 9, 19), date(2027, 6, 1)]:
            answer = calendar.resolve(asked, ticker="IBM")
            print(f"  asked about {asked}  ->  {answer.status}")
            print(f"    {answer.explain()}")

        print("\nThe Saturday falls back to Friday and says so. A future date does")
        print("not fall back at all, because that would turn 'no data yet' into a")
        print("confident stale price.")

        heading(7, "Report coverage honestly")

        universe = load_universe(US_UNIVERSE)
        print(f"  {len(universe)} securities in the US universe")
        print(f"  benchmark: {benchmark(universe).ticker} ({benchmark(universe).name})")
        print("  names and SEC identifiers read from the SEC, never typed by hand\n")

        markdown = build_coverage_markdown(store, {"US": universe}, generated_on=date.today())
        held = [line for line in markdown.splitlines() if line.startswith("| IBM")]
        print("  the generated COVERAGE.md row for the one stock we loaded:")
        print(f"  {held[0] if held else '(IBM is not in the universe, so it is flagged instead)'}")
        gap = "In the database but not in the universe" in markdown
        print(f"\n  flagged as outside the universe: {gap}")
        print("  Coverage is generated from the database, so it cannot claim")
        print("  more than is actually there.")

    print(f"\n{'=' * 70}")
    print(" Nothing above touched the network or a language model.")
    print(" Next: the eval set, then the agent that answers from this data.")
    print(f"{'=' * 70}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
