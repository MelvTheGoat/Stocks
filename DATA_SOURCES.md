# Data sources

Every source this project uses, what it gives us, and what its terms allow.
Nothing gets collected until it has an entry here.

All checks below were run on **2026-09-27 and 2026-09-28** from the
development container. Where a check could not be completed, this file says so
rather than assuming. A source's behaviour can depend on who is asking, so the
`probe-sources` workflow re-runs the reachability checks from a GitHub Actions
runner, where the answers may differ.

A note on how to read this: "robots.txt" is a file a website publishes saying
which parts automated programs may read. "WAF" is a web application firewall,
a filter in front of a site that blocks traffic it thinks is automated.

---

## Nigerian Exchange (NGX)

### ngxgroup.com — the main public website

**Status: blocked. Not in use.**

This was the intended source for the daily equities price list. It does not
work, and the reason matters.

| Check | Result |
| --- | --- |
| `https://ngxgroup.com/robots.txt` | 404 — no crawl policy published |
| `https://ngxgroup.com/exchange/data/equities-price-list/` | HTTP 307 to a JavaScript bot challenge |
| `https://ngxgroup.com/` and every other path tried | same 307 challenge |
| Server header | `Sucuri/Cloudproxy` |

The whole site sits behind a Sucuri WAF. Every request is answered with a small
HTML page that runs JavaScript, sets a `sucuri_cloudproxy_*` cookie and
reloads. A plain HTTP client never gets past it.

Two consequences, and they are separate:

1. **Technically blocked.** A GitHub Actions runner would meet the same
   challenge. Actions IP ranges are widely known and tend to be treated more
   harshly by bot filters, not less.
2. **Terms could not be verified.** `/terms/`, `/terms-and-conditions/`,
   `/privacy-policy/`, `/disclaimer/` and `/data-pricing-policies-contracts/`
   are all behind the same challenge, so the terms of use could not be read.
   With no robots.txt either, there is no published statement to rely on.

Getting past the challenge would mean executing the anti-bot JavaScript or
replaying its cookie. That is working around a measure the site put there
deliberately, so it is not on the table.

### dataportal.ngxgroup.com — X-DataPortal

**Status: not usable. Requires an account.**

Reachable (not behind the challenge), but it is a login wall: the page posts to
`/Home/AuthenticateUser` and offers registration and password recovery. This is
NGX's data product, sold under "Data Pricing, Policies & contracts" on the main
site. Paid data is out of scope for this project.

### Other NGX subdomains

`doc.ngxgroup.com`, `api.ngxgroup.com` and `data.ngxgroup.com` do not resolve.

### african-markets.com — a possible substitute

**Status: candidate, terms not yet confirmed.**

| Check | Result |
| --- | --- |
| `robots.txt` | Present. Blocks only CMS internals (`/administrator/`, `/cache/`, `/modules/` and similar). `/en/stock-markets/` is **not** disallowed. |
| `/en/stock-markets/ngse/listed-companies` | HTTP 200, serves structured data including ticker and ISIN for NGX listings (DANGCEM, GTCO, MTNN and the rest). |
| Terms of use page | Not found. `/en/terms-of-use` and `/en/terms` return 404, `/en/disclaimer` returns a server error. |

So robots.txt permits it, but there is no terms page to check, which is not the
same as permission. This needs a human decision before anything is collected
from it. It is also a third party republishing NGX figures, not the exchange
itself, so any data from here would need to be labelled as second-hand in
COVERAGE.md.

---

## United States

### SEC EDGAR - company facts and the ticker list

**Status: in use. Public domain.**

US government work, so the data carries no copyright. The SEC asks for a
contact email address in the User-Agent and rate-limits to 10 requests per
second.

| Check | Result |
| --- | --- |
| Request with no contact address | HTTP 403 |
| Same request with `User-Agent: stockagent/0.1 (<email>)` | HTTP 200 |

The 403 is their documented fair-access policy, not a block. The address comes
from the `SEC_EMAIL` secret. `scripts/build_us_universe.py` already uses this
to pull official company names and central index keys, so no company name in
this project is typed from memory.

### Alpha Vantage - cross-check source

**Status: in use for cross-checking only. Free tier verified.**

| Check | Result |
| --- | --- |
| `TIME_SERIES_DAILY_ADJUSTED` | HTTP 200, with adjusted close, dividend amount and split coefficient |
| `DIVIDENDS` | HTTP 200, with declaration, ex, record and payment dates |
| `SPLITS` | HTTP 200 |
| Free tier limit, from their pricing page | **25 API requests per day** |

Everything needed is on the free tier, but 25 requests a day is the binding
constraint. A full backfill of 55 securities across three endpoints is 165
requests, so about a week of waiting, and a daily refresh would need 55 a day.

That rules it out as the bulk source and suits it well as the second opinion:
25 requests a day is plenty to re-check a rotating sample, which is all a
cross-check needs. Saved sample responses are in
`data/samples/alphavantage/` and the parser is tested against them.

A quiet trap worth recording: a rate-limited request returns **HTTP 200** with
a JSON object containing a polite sentence instead of data. Parsed carelessly
that looks like a stock which never traded. The parser raises on it instead.

### Twelve Data - candidate bulk source

**Status: candidate. Needs a free API key.**

| Check | Result |
| --- | --- |
| `time_series` with the demo key | HTTP 200, real daily OHLC for AAPL |
| Free "Basic" plan, from their pricing page | 8 requests per minute |

The free tier is far roomier than Alpha Vantage's, which makes it the
realistic candidate for collecting all 55 securities. Dividends and splits are
separate endpoints, so a full refresh is roughly 165 calls, comfortably inside
an 8-per-minute budget spread over half an hour.

Not adopted yet: it needs a free account, and only the per-minute limit has
been confirmed, not the daily one.

### Stooq - unresolved

**Status: cannot confirm. No valid sample seen.**

Reachable once in about six attempts from the development container, and that
one response was 796 bytes, far too small to be a full daily history. Every
other attempt failed with a connection error at the egress proxy.

No parser has been written for it, deliberately. Writing one would mean
guessing at a CSV layout never actually observed, and a parser built on a
guess is a fabricated fact with code wrapped around it. The `probe-sources`
workflow will settle whether a GitHub Actions runner can reach it.

### Yahoo Finance - reachable, not used

**Status: deliberately not used.**

`query1.finance.yahoo.com/v8/finance/chart/...` returns HTTP 200 with prices,
dividends and splits in one call, no API key, no rate limit encountered.
Technically it is the easiest option by a wide margin.

It is not used because the endpoint is undocumented and Yahoo's terms of
service restrict automated access and redistribution. Plenty of research
projects use it anyway. This one publishes its sources and claims to respect
their terms, so it cannot.

---

## Rules this file exists to enforce

- No paid data, and no free tier that turns into a bill.
- No source whose terms forbid automated collection.
- No republishing raw data where the terms forbid it. Where that applies, the
  data goes to a private Hugging Face dataset and only derived figures are
  published.
- Every source named here, with the date its terms were checked.
