"""Fill the database with US prices, dividends and splits.

Safe to run again. Writes are merges on each record's key, and a security whose
history already reaches the as-of date is skipped, so a run that is interrupted
after thirty securities resumes at the thirty-first rather than starting over.
That matters because the free tier allows eight requests a minute, so a full
collection takes around twenty minutes and will get interrupted sooner or later.

The collected database is never committed. Twelve Data licenses the data for
internal use and not for redistribution, so the repository carries this script
instead: anyone with their own free key rebuilds an identical database with one
command.

Usage:
    export TWELVEDATA_API_KEY=...
    python scripts/collect_us.py --start 2019-01-01
    python scripts/collect_us.py --dry-run          # show the plan, call nothing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from stockagent.data.sources.twelvedata import RateLimited, TwelveDataError
from stockagent.data.sources.twelvedata_client import TwelveDataClient
from stockagent.data.store import MarketStore
from stockagent.data.universe import US_UNIVERSE, UniverseEntry, load_universe

DATABASE = Path("data/db")
REPORT = Path("data/db/collection_report.json")

# Three calls per security: prices, dividends, splits.
CALLS_PER_SECURITY = 3


@dataclass
class Outcome:
    collected: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    bars_written: int = 0
    requests_made: int = 0

    def as_dict(self, as_of: date, start: date) -> dict:
        return {
            "as_of": as_of.isoformat(),
            "start": start.isoformat(),
            "collected": sorted(self.collected),
            "skipped": sorted(self.skipped),
            "failed": self.failed,
            "bars_written": self.bars_written,
            "requests_made": self.requests_made,
        }


def default_as_of() -> date:
    """Yesterday.

    Today's bar is incomplete while the market is open: the provider returns it
    with a partial volume and a close that is really the last trade so far.
    Storing that as a closing price would put a wrong number in the database
    and, worse, make an eval answer change between runs. Yesterday is always
    settled.
    """
    return date.today() - timedelta(days=1)


def already_current(store: MarketStore, ticker: str, as_of: date) -> bool:
    rows = store.query(
        "SELECT max(day) FROM bars WHERE market = 'US' AND ticker = ?", [ticker]
    )
    latest = rows[0][0] if rows else None
    return latest is not None and latest >= as_of


def collect_one(
    client: TwelveDataClient,
    store: MarketStore,
    entry: UniverseEntry,
    *,
    start: date,
    as_of: date,
) -> int:
    """Collect one security. Returns the number of bars written."""
    bars = client.time_series(entry.ticker, start=start, end=as_of)
    # A bar dated after the as-of date would undo the point of freezing one.
    bars = [bar for bar in bars if bar.day <= as_of]

    dividends = client.dividends(entry.ticker, start=start, end=as_of)
    # Splits are fetched from well before the price window, because a split
    # inside the window needs the action even if it predates the first bar we
    # keep. Adjusted returns are wrong without it.
    splits = client.splits(entry.ticker, start=date(1990, 1, 1), end=as_of)

    if bars:
        store.write_bars(bars)
    if dividends:
        store.write_dividends(dividends)
    if splits:
        store.write_actions(splits)
    return len(bars)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2019, 1, 1))
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=default_as_of(),
        help="last day to collect; defaults to yesterday, since today is unsettled",
    )
    parser.add_argument("--only", help="comma-separated tickers, for a partial run")
    parser.add_argument("--limit", type=int, help="stop after this many securities")
    parser.add_argument("--force", action="store_true", help="re-collect even if current")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, call nothing")
    args = parser.parse_args(argv)

    if args.as_of >= date.today():
        print("--as-of must be before today; today's prices are not settled yet")
        return 1

    entries = load_universe(US_UNIVERSE)
    if args.only:
        wanted = {ticker.strip().upper() for ticker in args.only.split(",")}
        entries = [entry for entry in entries if entry.ticker in wanted]
        missing = wanted - {entry.ticker for entry in entries}
        if missing:
            print(f"not in the universe: {', '.join(sorted(missing))}")
            return 1
    if args.limit:
        entries = entries[: args.limit]

    store = MarketStore(DATABASE)
    outcome = Outcome()

    todo = [
        entry
        for entry in entries
        if args.force or not already_current(store, entry.ticker, args.as_of)
    ]
    outcome.skipped = [e.ticker for e in entries if e not in todo]

    calls = len(todo) * CALLS_PER_SECURITY
    print(
        f"universe: {len(entries)}  to collect: {len(todo)}  "
        f"already current: {len(outcome.skipped)}"
    )
    print(f"window: {args.start} to {args.as_of}")
    print(f"about {calls} requests, roughly {calls / 8:.0f} minutes at eight a minute")

    if args.dry_run:
        print("\ndry run, nothing called. Tickers:")
        print("  " + ", ".join(entry.ticker for entry in todo))
        return 0

    api_key = os.environ.get("TWELVEDATA_API_KEY", "").strip()
    if not api_key:
        print("\nTWELVEDATA_API_KEY is not set.")
        return 1

    client = TwelveDataClient(api_key=api_key)
    try:
        for index, entry in enumerate(todo, start=1):
            try:
                written = collect_one(
                    client, store, entry, start=args.start, as_of=args.as_of
                )
            except RateLimited as error:
                # The budget is gone for now. Stopping leaves everything
                # collected so far in place; the next run resumes here.
                print(f"\nstopped at {entry.ticker}: {error}")
                outcome.failed[entry.ticker] = f"rate limited: {error}"
                break
            except TwelveDataError as error:
                # One bad symbol must not end the run.
                print(f"  {index:>3}/{len(todo)} {entry.ticker:<8} FAILED {error}")
                outcome.failed[entry.ticker] = str(error)
                continue

            outcome.collected.append(entry.ticker)
            outcome.bars_written += written
            print(f"  {index:>3}/{len(todo)} {entry.ticker:<8} {written:>5} bars")
    finally:
        outcome.requests_made = client.requests_made
        client.close()
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(outcome.as_dict(args.as_of, args.start), indent=2))

    print(
        f"\ncollected {len(outcome.collected)}, failed {len(outcome.failed)}, "
        f"{outcome.bars_written} bars, {outcome.requests_made} requests"
    )
    if outcome.failed:
        print("failures are listed in " + str(REPORT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
