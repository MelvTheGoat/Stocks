"""Check which data sources are reachable from wherever this runs.

Two questions are open and neither can be settled from a development
container, because what a source does depends on who is asking:

* Does an NGX page come back as data, or as the Sucuri bot challenge?
* Is Stooq reachable at all?

A GitHub Actions runner has a different address and a different reputation
from this container, so the answer may differ there. This script asks once,
politely, and prints what came back. It collects nothing and parses nothing.

Run it locally with `python scripts/probe_sources.py`, or from the
"probe-sources" workflow.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import httpx

USER_AGENT = "stockagent-probe/0.1 (research project; contact via github.com/MelvTheGoat/Stocks)"
TIMEOUT = 25.0

# The SEC's fair-access policy asks for a contact email address in the
# User-Agent and answers 403 without one. That is documented behaviour, not a
# block, so the probe supplies the address when it has been configured and
# says plainly when it has not.
SEC_EMAIL = os.environ.get("SEC_EMAIL", "").strip()


@dataclass(frozen=True)
class Probe:
    name: str
    url: str
    note: str
    headers: dict[str, str] | None = None


PROBES = [
    Probe(
        "NGX price list",
        "https://ngxgroup.com/exchange/data/equities-price-list/",
        "307 plus a JavaScript page means the bot challenge; 200 with real HTML means data",
    ),
    Probe("NGX home", "https://ngxgroup.com/", "same challenge check on a simpler page"),
    Probe(
        "Stooq daily CSV",
        "https://stooq.com/q/d/l/?s=aapl.us&i=d",
        "unreachable from the dev container; may work here",
    ),
    Probe(
        "Alpha Vantage",
        "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&apikey=demo",
        "demo key, IBM only; checks reachability not entitlement",
    ),
    Probe(
        "SEC EDGAR",
        "https://www.sec.gov/files/company_tickers.json",
        (
            "403 without an email in the User-Agent is their documented policy, not a block"
            if SEC_EMAIL
            else "SEC_EMAIL is not set, so a 403 here is expected and means nothing"
        ),
        headers={"User-Agent": f"stockagent-probe/0.1 ({SEC_EMAIL})"} if SEC_EMAIL else None,
    ),
    Probe(
        "African Markets NGX",
        "https://african-markets.com/en/stock-markets/ngse/listed-companies",
        "possible NGX substitute; robots.txt permits this path",
    ),
]


def looks_like_bot_challenge(response: httpx.Response) -> bool:
    body = response.text[:4000].lower()
    return "sucuri" in body or "javascript is required" in body


def probe(client: httpx.Client, item: Probe) -> tuple[str, str]:
    try:
        response = client.get(item.url, headers=item.headers)
    except httpx.HTTPError as error:
        return "unreachable", type(error).__name__

    size = len(response.content)
    if looks_like_bot_challenge(response):
        return "bot challenge", f"HTTP {response.status_code}, {size} bytes"
    if response.status_code >= 400:
        return "error", f"HTTP {response.status_code}, {size} bytes"
    return "ok", f"HTTP {response.status_code}, {size} bytes"


def main() -> int:
    headers = {"User-Agent": USER_AGENT}
    results = []
    with httpx.Client(headers=headers, timeout=TIMEOUT, follow_redirects=True) as client:
        for item in PROBES:
            verdict, detail = probe(client, item)
            results.append((item, verdict, detail))

    width = max(len(item.name) for item in PROBES)
    print(f"{'source'.ljust(width)}  {'verdict'.ljust(13)}  detail")
    print("-" * (width + 40))
    for item, verdict, detail in results:
        print(f"{item.name.ljust(width)}  {verdict.ljust(13)}  {detail}")

    print("\nnotes")
    for item, _, _ in results:
        print(f"  {item.name}: {item.note}")

    # Always exits 0. A source being unreachable is a finding to read, not a
    # broken build.
    return 0


if __name__ == "__main__":
    sys.exit(main())
