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

**Status: RULED OUT. Their terms forbid it.**

This was to be the source for the daily equities price list. It cannot be
used, and the reason is the terms of use rather than anything technical.

NGX's Terms and Conditions, at <https://ngxgroup.com/terms/>, say:

> You shall not conduct any systematic or automated data collection activities
> (including scraping, data mining, data extraction and data harvesting) on or
> in relation to the Website without NGX Group's/its Affiliates' express
> written consent

and, separately:

> You shall not, and shall not attempt to, copy, reproduce, republish, frame,
> upload to a third party, transmit or distribute the whole or any part of this
> Website.

That is the exact activity the daily collector would have performed, and the
exact publication the `ngx-data` branch would have been. Both are prohibited
without express written consent. So no collector was built.

The terms do name the way through: **express written consent.** Asking NGX for
permission for a non-commercial research project is the only route to
first-party NGX data that respects this, and it costs nothing to ask.

#### How this was established, and a near miss worth recording

The site sits behind a Sucuri web application firewall. From the development
container every request returned HTTP 307 and a JavaScript bot challenge, so
the terms page could not be read at all. A GitHub Actions runner is served the
real pages, so the check ran there instead.

The first run reported "no wording about automated access or redistribution
found" for the terms page. That was **wrong, and it was nearly believed.** The
server replies with `content-encoding: br`, the runner had no brotli decoder,
and the body came back as 60 KB of binary noise — which a keyword search
naturally finds nothing in, while still reporting a plausible character count.
A decoding failure had produced a clean bill of health.

The fix was to request only encodings that always decode, and to check that a
body looks like text before drawing any conclusion from it. The corrected run
found the clauses above in the first pass. Had the bug gone unnoticed, this
file would have recorded permission that does not exist.

### dataportal.ngxgroup.com — X-DataPortal

**Status: not usable. Account required, and it is the paid product.**

Reachable, and not behind the firewall challenge, but it is a login wall:
the page posts to `/Home/AuthenticateUser` and offers registration. This is
NGX's commercial data service, sold under "Data Pricing, Policies &
contracts". Paid data is out of scope.

This is consistent with the terms: NGX licenses its market data, which is
precisely why the website forbids taking it for free.

### Other NGX subdomains

`doc.ngxgroup.com`, `api.ngxgroup.com` and `data.ngxgroup.com` do not resolve.

### african-markets.com — not usable either

**Status: ruled out on the same grounds, one step removed.**

Reachable, and its robots.txt permits `/en/stock-markets/`. It serves NGX
tickers with ISINs.

It is not usable, for two reasons that only became clear once NGX's terms were
read. It has no terms of use page at all (`/en/terms-of-use` returns 404,
`/en/disclaimer` a server error), so there is nothing to check. And it is a
third party republishing NGX figures, while NGX forbids republication of its
data. Whether they hold a licence to do so is unknown, and collecting from
them would mean relying on rights that have not been shown to exist.

### What this means for the project

The Nigerian half of this project is blocked on permission, not on code. The
database, the trading calendar and the record types are all market-agnostic
and already carry `market` and `currency` on every row, so NGX data would slot
in unchanged the day consent arrives.

Until then the honest position is the one written down here: we wanted
first-party Nigerian market data, the exchange's terms prohibit collecting it
without written consent, and we did not collect it.

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

### Twelve Data - in use as the bulk source

**Status: in use. Free tier. Data may NOT be published.**

| Check | Result |
| --- | --- |
| `time_series` | HTTP 200, daily open/high/low/close/volume |
| `dividends` | HTTP 200, ex-date and amount |
| `splits` | HTTP 200, with `from_factor`, `to_factor` and a description |
| Free "Basic" plan, from their pricing page | 8 requests per minute |

Three behaviours are recorded here because each one produces a wrong number
rather than an error:

**The split factor is ambiguous in the response.** Apple's 2020 split arrives
as `{"ratio": 0.25, "from_factor": 4, "to_factor": 1, "description": "4-for-1
split"}`. Taking `ratio` as the factor inverts every split-adjusted return and
nothing fails. The parser uses `from_factor / to_factor` and then checks the
result against the number in the description, refusing to parse if they
disagree.

**`end_date` is exclusive.** A request for the 14th to the 29th returns nothing
dated the 29th. The client sends one day later than asked so no caller has to
remember.

**There is no adjusted close.** Prices come as quoted, so adjusting for splits
and dividends is our own job. That is more work and better for this project:
the eval asks about split-adjusted returns, so the adjustment is part of what
is being measured and should not be a vendor's undocumented convention.

Also worth knowing: the last bar is the day in progress while the market is
open, carrying a partial volume and a "close" that is only the latest trade.
The collector defaults its as-of date to yesterday for that reason.

#### Their terms, and where the data is therefore kept

Twelve Data's Terms of Use, at <https://twelvedata.com/terms>, grant a licence
to "Access, receive, process, and store Data solely for Internal Use", and
define Internal Use as "use solely for Customer's internal business purposes
and **not for redistribution** or external commercial purposes". Section 2.3
then prohibits the Customer from:

> Redistribute, resell, sublicense, or transfer any Data or access rights to
> third parties except as expressly permitted by your Subscription Tier, Data
> Add-ons, or a separate agreement with Twelve Data

with "Redistribution" defined as "any publication, distribution, or provision
of Data to third parties". The free tier carries no redistribution add-on.

So committing the collected prices to this public repository would breach the
licence. Two consequences, both already in force:

- `data/db/` is in `.gitignore`. The database is never committed, and no
  workflow uploads it as an artifact of a public repository, since anyone who
  can see the repository could download that.
- **Ground truth is computed, not stored.** The eval set holds question text
  and parameters; the correct answers are worked out at run time by reference
  code reading whoever's local database. A committed answer like "AAPL closed
  at 338.40" would be redistribution; the question "what did AAPL close at on
  28 September 2026" is not.

The licence does permit "Derived Data that cannot be reverse-engineered to
recreate the original Data", which is what every published result in this
project is: accuracy rates, error counts, latency figures, and the date ranges
and row counts in COVERAGE.md.

Reproducibility survives this intact. Anyone with their own free key runs
`python scripts/collect_us.py` and gets a byte-identical database, then every
number in the report regenerates. That is a better arrangement than shipping a
copy of someone else's data and hoping nobody reads the licence.

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
