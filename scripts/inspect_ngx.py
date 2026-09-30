"""Read NGX's public pages once, and report what they say.

The development container is served a bot challenge by NGX's firewall, so from
there the terms of use could not be read and the price list could not be seen.
A GitHub Actions runner is served the real pages. This script runs there, and
does two jobs that have to happen before any collector is written:

1. **Settle the terms question.** Fetch robots.txt and every terms, disclaimer
   and data-policy page, and print what they actually say about automated
   access and redistribution. Until that has been read, rule 8 cannot be
   satisfied, and no collector should exist.

2. **Save the equities price list as it really is.** A parser written against
   a guessed page structure is a fabricated fact with code around it. The saved
   HTML becomes a test fixture, and the parser is written against that.

A handful of requests, run once, with a contact address in the User-Agent.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

BASE = "https://ngxgroup.com"
USER_AGENT = "stockagent/0.1 (research project; github.com/MelvTheGoat/Stocks)"
OUTPUT = Path("ngx-capture")

# Ask only for encodings every httpx install can decode. The first run of this
# script asked for anything, got brotli back, had no brotli decoder, and wrote
# 60 KB of binary noise to the artifact -- while still reporting a plausible
# character count for every page. That nearly turned a decoding failure into a
# finding about what NGX's terms permit. Naming two safe encodings removes the
# whole failure mode rather than detecting it.
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}

# If a page still comes back undecodable, say so instead of analysing noise.
PRINTABLE = re.compile(r"[\t\n\r\x20-\x7e]")


def is_readable(text: str) -> bool:
    """True if the text looks like text rather than a failed decode."""
    if not text:
        return False
    sample = text[:4000]
    return len(PRINTABLE.findall(sample)) / len(sample) > 0.85

PRICE_LIST = "/exchange/data/equities-price-list/"

TERMS_PAGES = [
    "/robots.txt",
    "/terms/",
    "/terms-of-use/",
    "/terms-and-conditions/",
    "/disclaimer/",
    "/privacy-policy/",
    "/data-pricing-policies-contracts/",
    "/data/",
]

# Words that would decide whether a collector may be written at all.
RESTRICTION_WORDS = re.compile(
    r"(scrap\w*|crawl\w*|robot\w*|spider|automat\w*|bot\b|data[- ]?min\w*|"
    r"redistribut\w*|re-?publish\w*|reproduc\w*|resell\w*|commercial\w*|"
    r"personal use|non-?commercial|without .{0,30}consent|prior written)",
    re.IGNORECASE,
)


def strip_tags(html: str) -> str:
    without_script = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", without_script)
    return re.sub(r"\s+", " ", text).strip()


def heading(text: str) -> None:
    print(f"\n{'=' * 72}\n {text}\n{'=' * 72}")


def report_terms(client: httpx.Client) -> None:
    heading("Terms, robots.txt and data policy")
    OUTPUT.mkdir(parents=True, exist_ok=True)

    for path in TERMS_PAGES:
        url = BASE + path
        try:
            response = client.get(url)
        except httpx.HTTPError as error:
            print(f"\n--- {path}: unreachable ({type(error).__name__})")
            continue

        encoding = response.headers.get("content-encoding", "none")
        if response.status_code >= 400:
            print(f"\n--- {path}: HTTP {response.status_code} (page does not exist)")
            continue

        body = response.text
        if not is_readable(body):
            print(
                f"\n--- {path}: HTTP {response.status_code} but the body did not decode "
                f"(content-encoding: {encoding}). Nothing can be concluded from it."
            )
            continue

        if "sucuri" in body[:4000].lower() or "javascript is required" in body[:4000].lower():
            print(f"\n--- {path}: still the bot challenge, could not read")
            continue

        if path.endswith(".txt"):
            print(f"\n--- {path}: HTTP {response.status_code}, verbatim below")
            print(body[:2000])
            continue

        text = strip_tags(body)
        # Saved so the terms can be read in full rather than trusted to a
        # keyword search. A grep finding nothing is weak evidence; the text
        # itself is the evidence.
        slug = path.strip("/").replace("/", "-") or "home"
        (OUTPUT / f"terms-{slug}.txt").write_text(text)
        matches = []
        for match in RESTRICTION_WORDS.finditer(text):
            start, end = max(0, match.start() - 180), min(len(text), match.end() + 180)
            matches.append(text[start:end])

        print(f"\n--- {path}: HTTP {response.status_code}, {len(text)} chars of text")
        if not matches:
            print("    no wording about automated access or redistribution found")
            continue
        # De-duplicate overlapping windows so the output stays readable.
        seen: list[str] = []
        for snippet in matches:
            if any(snippet[:80] in already for already in seen):
                continue
            seen.append(snippet)
        for snippet in seen[:12]:
            print(f"    ...{snippet}...")


def report_price_list(client: httpx.Client) -> None:
    heading("The equities price list, as it actually is")

    url = BASE + PRICE_LIST
    response = client.get(url)
    encoding = response.headers.get("content-encoding", "none")
    print(
        f"HTTP {response.status_code}, {len(response.content)} bytes, "
        f"content-type: {response.headers.get('content-type', '?')}, "
        f"content-encoding: {encoding}"
    )

    body = response.text
    if not is_readable(body):
        print(f"the body did not decode (content-encoding: {encoding}); not analysing noise")
        return
    if "sucuri" in body[:4000].lower():
        print("still the bot challenge; nothing to save")
        return

    OUTPUT.mkdir(parents=True, exist_ok=True)
    saved = OUTPUT / "equities_price_list.html"
    saved.write_text(body)
    print(f"saved to {saved} ({len(body)} chars)")

    tables = re.findall(r"(?is)<table.*?</table>", body)
    print(f"\n{len(tables)} <table> elements found")
    for index, table in enumerate(tables[:4]):
        headers = re.findall(r"(?is)<th[^>]*>(.*?)</th>", table)
        cleaned = [strip_tags(h) for h in headers]
        rows = len(re.findall(r"(?is)<tr", table))
        print(f"\n  table {index}: {rows} rows")
        if cleaned:
            print(f"    headers: {cleaned}")
        first_row = re.search(r"(?is)<tr[^>]*>(?:(?!</tr>).)*?<td.*?</tr>", table)
        if first_row:
            cells = [strip_tags(c) for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>", first_row[0])]
            print(f"    first data row: {cells}")

    # Some NGX pages load their table over AJAX rather than serving it inline.
    # If so, the endpoint matters more than the HTML.
    endpoints = set(
        re.findall(r"""(?i)(?:url|ajax)\s*:\s*['"]([^'"]{4,200})['"]""", body)
    ) | set(re.findall(r"""(?i)(admin-ajax\.php|wp-json/[\w/-]+)""", body))
    if endpoints:
        print("\npossible data endpoints referenced by the page:")
        for endpoint in sorted(endpoints)[:20]:
            print(f"    {endpoint}")

    csv_links = set(re.findall(r"""(?i)href=["']([^"']+\.(?:csv|xlsx?|json))["']""", body))
    if csv_links:
        print("\ndownload links on the page:")
        for link in sorted(csv_links)[:20]:
            print(f"    {link}")


def main() -> int:
    with httpx.Client(headers=HEADERS, timeout=40.0, follow_redirects=True) as client:
        report_terms(client)
        report_price_list(client)

    print("\nRead the terms output above before any collector is written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
