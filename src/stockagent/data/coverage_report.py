"""Generates COVERAGE.md from the database.

Written by a program rather than by hand, on purpose. A hand-written coverage
file records what someone believed the pipeline collected. A generated one
records what is actually in the database. Those drift apart the first time a
collection run half-fails, and the hand-written version is the one that ends
up in the report.

The file says what is missing as loudly as what is present. A universe entry
with no data at all gets its own line; so does a security whose history stops
early. Coverage that only lists successes is marketing.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timezone

from stockagent.data.store import Coverage, MarketStore
from stockagent.data.universe import UniverseEntry


def _table(header: Iterable[str], rows: Iterable[Iterable[str]]) -> list[str]:
    header = list(header)
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines


def _market_section(
    market: str,
    entries: list[UniverseEntry],
    coverage: dict[str, Coverage],
) -> list[str]:
    lines = [f"## {market}", ""]

    expected = {entry.ticker for entry in entries}
    held = set(coverage)
    missing = sorted(expected - held)
    unexpected = sorted(held - expected)

    lines += [
        f"{len(entries)} securities in the universe, {len(held & expected)} with price data.",
        "",
    ]

    if held & expected:
        rows = []
        for entry in sorted(entries, key=lambda e: e.ticker):
            row = coverage.get(entry.ticker)
            if row is None:
                continue
            rows.append(
                [
                    entry.ticker,
                    entry.name,
                    row.first_day.isoformat(),
                    row.last_day.isoformat(),
                    str(row.trading_days),
                    ", ".join(row.sources),
                ]
            )
        lines += _table(
            ["ticker", "name", "from", "to", "trading days", "sources"], rows
        )
        lines.append("")

    if missing:
        lines += [
            "### No data at all",
            "",
            "In the universe, nothing collected:",
            "",
            *(f"- {ticker}" for ticker in missing),
            "",
        ]

    if unexpected:
        lines += [
            "### In the database but not in the universe",
            "",
            "Left over from an earlier universe, or collected by mistake:",
            "",
            *(f"- {ticker}" for ticker in unexpected),
            "",
        ]

    if not held:
        lines += ["No price data has been collected for this market yet.", ""]

    return lines


def build_coverage_markdown(
    store: MarketStore,
    universes: dict[str, list[UniverseEntry]],
    *,
    generated_on: date | None = None,
) -> str:
    """Render COVERAGE.md for every market named in `universes`."""
    by_market: dict[str, dict[str, Coverage]] = {}
    for row in store.coverage():
        by_market.setdefault(row.market, {})[row.ticker] = row

    stamp = (generated_on or datetime.now(timezone.utc).date()).isoformat()

    lines = [
        "# Coverage",
        "",
        "What the database actually holds, per market and per security.",
        "",
        f"Generated from the database on {stamp}. Do not edit by hand: run",
        "`python scripts/write_coverage.py` instead, or the next run will",
        "overwrite whatever was written here.",
        "",
    ]

    for market in sorted(universes):
        lines += _market_section(market, universes[market], by_market.get(market, {}))

    absent = sorted(set(by_market) - set(universes))
    for market in absent:
        lines += [
            f"## {market}",
            "",
            "Data present, but no universe file defines what was meant to be here.",
            "",
        ]

    return "\n".join(lines).rstrip() + "\n"
