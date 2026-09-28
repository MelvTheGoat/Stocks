"""Write the list of US securities the project covers.

The tickers below are chosen by hand for spread across industries, long
trading histories and enough corporate actions between them to exercise the
split and dividend handling. Everything else about each one -- the official
name, the SEC central index key, the exchange -- is read from the SEC's own
ticker file rather than typed in, because a company name typed from memory is
a fabricated fact, and this project cannot afford any of those.

A ticker that does not resolve against the SEC file is reported and left out.
Silently dropping it would leave the universe quietly smaller than the
documentation claims.

Run: SEC_EMAIL=you@example.com python scripts/build_us_universe.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

SEC_TICKERS = "https://www.sec.gov/files/company_tickers_exchange.json"
OUTPUT = Path("data/universe/us.json")

# The market benchmark. Kept separate from the companies because questions
# like "did it beat the market" treat it differently.
BENCHMARK = "SPY"

TICKERS = [
    # Technology and communications
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "ORCL",
    "CRM", "ADBE", "INTC", "CSCO", "AMD", "QCOM", "TXN", "IBM",
    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "AXP", "BLK", "SCHW",
    # Health care
    "JNJ", "UNH", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT",
    # Consumer
    "PG", "KO", "PEP", "WMT", "COST", "MCD", "NKE", "HD",
    # Industrials and energy
    "XOM", "CVX", "CAT", "BA", "GE", "UNP", "HON", "LMT",
    # Telecoms, utilities and payments
    "T", "VZ", "NEE", "DIS", "V", "MA",
]


def fetch_sec_tickers(email: str) -> dict[str, dict]:
    """Ticker -> {name, cik, exchange}, from the SEC's published file."""
    headers = {"User-Agent": f"stockagent/0.1 ({email})"}
    response = httpx.get(SEC_TICKERS, headers=headers, timeout=60.0)
    response.raise_for_status()
    payload = response.json()

    columns = payload["fields"]
    index = {name: position for position, name in enumerate(columns)}
    table = {}
    for row in payload["data"]:
        ticker = row[index["ticker"]]
        table[ticker] = {
            "name": row[index["name"]],
            "cik": row[index["cik"]],
            "exchange": row[index["exchange"]],
        }
    return table


def main() -> int:
    email = os.environ.get("SEC_EMAIL", "").strip()
    if not email:
        print("SEC_EMAIL must be set: the SEC answers 403 without a contact address.")
        return 1

    sec = fetch_sec_tickers(email)

    securities, missing = [], []
    for ticker in [*TICKERS, BENCHMARK]:
        found = sec.get(ticker)
        if found is None:
            missing.append(ticker)
            continue
        securities.append(
            {
                "ticker": ticker,
                "market": "US",
                "currency": "USD",
                "name": found["name"],
                "cik": found["cik"],
                "exchange": found["exchange"],
                "role": "benchmark" if ticker == BENCHMARK else "company",
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(securities, indent=2, sort_keys=True) + "\n")

    print(f"wrote {len(securities)} securities to {OUTPUT}")
    if missing:
        print(f"NOT FOUND in the SEC file, left out: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
