"""Check which data sources are reachable from wherever this runs.

What a source does depends on who is asking: an address that a firewall likes
gets data, one it does not gets a challenge page. A GitHub Actions runner and
this development container are treated differently, so a reachability question
can only be answered where the collection will actually happen. This script
asks once, politely, and prints what came back. It collects nothing and parses
nothing.

The open question it exists for is Stooq, which is reachable from the
development container roughly one attempt in six.

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



# NGX is deliberately absent. Its terms of use forbid systematic or automated
# data collection without written consent, so whether a runner can reach it is
# no longer a useful question. See DATA_SOURCES.md.
PROBES = [
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
