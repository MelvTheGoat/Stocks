# Data sources

Every source this project uses, what it gives us, and what its terms allow.
Nothing gets collected until it has an entry here.

All checks below were run on **2026-09-27** from the development container.
Where a check could not be completed, this file says so rather than assuming.

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

Not yet investigated. Planned for Phase 3.

| Source | Intended use | Terms checked |
| --- | --- | --- |
| SEC EDGAR | company facts, filings | not yet — needs a contact email in the User-Agent header, which SEC requires |
| A free price source, plus a second for cross-checking | daily prices, splits, dividends | not yet |

A first probe found `https://www.sec.gov/` returns 403 to a request with no
User-Agent, which is the documented SEC behaviour rather than a block: they
require a contact address in the header. That is what the `SEC_EMAIL` secret
is for.

---

## Rules this file exists to enforce

- No paid data, and no free tier that turns into a bill.
- No source whose terms forbid automated collection.
- No republishing raw data where the terms forbid it. Where that applies, the
  data goes to a private Hugging Face dataset and only derived figures are
  published.
- Every source named here, with the date its terms were checked.
