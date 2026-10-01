# Report

**Nothing here has been run on a GPU yet.** Every result is marked "not run yet"
and will stay that way until a real run fills it in. The structure is written in
advance so the results have somewhere honest to go, and so it is obvious
afterwards what was planned rather than found.

---

## The problem

A language model will tell you what Apple closed at on a Tuesday in 2019. It will
sound certain. Quite often it will be wrong, and nothing in the answer tells you
which time this is.

That is the failure this project is built around. The usual fix is to give the
model data and tools. The usual demonstration of the fix is a handful of good
examples, which proves very little: a system that works on five questions someone
chose is a system nobody has measured.

So this is built the other way round. The eval set, the reference answers and the
graders came first. The agent came second. Every number in this report points at a
run log.

### Why Nigerian stocks were in the plan

Models have read a great deal about Apple and very little about Nigerian
Breweries. That gap is the interesting part: it separates what a model remembers
from what it can work out. Comparing the two markets would have measured it
directly.

**That half of the project did not happen,** and the reason belongs in the report
rather than in a footnote. The Nigerian Exchange's terms of use prohibit
"systematic or automated data collection activities (including scraping, data
mining, data extraction and data harvesting)" without their express written
consent, and separately prohibit republishing any part of the site. The daily
collector would have done both. It was not built.

A smaller version of the same question survives on US data alone, by comparing a
closed-book baseline against a grounded one per question kind. See Experiment F in
[EXPERIMENTS.md](EXPERIMENTS.md).

A near miss worth recording. The first automated check of those terms reported
"no wording about automated access or redistribution found". That was wrong. The
site serves brotli-compressed pages, the checker had no brotli decoder, and it had
been searching 60 KB of binary noise while reporting a plausible character count.
A decoding failure had produced a clean bill of health. The corrected run found the
clauses immediately. Had the bug gone unnoticed, this project would have shipped a
scraper and a file claiming permission that does not exist.

---

## The data, and its gaps

| Market | Source | Status |
| --- | --- | --- |
| US prices, dividends, splits | Twelve Data, free tier | in use |
| US company names and identifiers | SEC EDGAR | in use, public domain |
| US cross-check | Alpha Vantage, free tier | cross-check only; 25 requests a day |
| NGX | the exchange's website | ruled out by their terms |

Full detail, including every check and its date, is in
[DATA_SOURCES.md](DATA_SOURCES.md). What the database actually holds is in
[COVERAGE.md](COVERAGE.md), which is generated from the database rather than
written by hand, so it cannot claim more than is there.

### Three traps in the data, all of which produce wrong numbers rather than errors

**The split factor arrives inverted in one field.** Apple's 2020 split comes back
as `{"ratio": 0.25, "from_factor": 4, "to_factor": 1}`. Reading `ratio` as the
factor makes every split-adjusted return wrong by sixteen for Apple, and nothing
fails. The parser derives the factor from `from_factor / to_factor` and then checks
it against the number written in the description, refusing to parse if they
disagree.

**`end_date` is exclusive.** A request for the 14th to the 29th returns nothing
dated the 29th. Silent, and it shows up months later as a stock that mysteriously
stops a day early.

**A rate-limited request returns HTTP 200** with a polite sentence instead of
data. Parsed carelessly it looks like a company that never traded, which is
indistinguishable from a real gap once it is in the database. Every parser checks
for it, and a test asserts that all of them do.

### Where the data lives, and why it is not here

Twelve Data licenses the data for "Internal Use ... not for redistribution".
Committing it to a public repository would breach that, so `data/db/` is in
`.gitignore` and the published results are derived figures only.

Reproducibility survives intact: anyone with their own free key runs
`python scripts/collect_us.py` and gets an identical database, then every number
below regenerates. **Ground truth is computed, not stored** — the eval file holds
question text and parameters, and the correct answers are worked out at run time
by reference code reading the local database. "What did AAPL close at on 28
September?" is publishable; the answer is not.

---

## The eval set

| | |
| --- | --- |
| Version | v1, not yet generated |
| As-of date | frozen per version |
| Generated questions | about 180 across eleven kinds |
| Hand-written cases | 24: advice, injection, unanswerable, Pidgin |
| Dev / test split | about two thirds / one third, by a hash of the question id |
| Hard document set | **not built**; see below |

### How it was built

Questions are generated from the database with a seed, so a version is
reproducible. Every generated question is then run through the reference
implementation and **dropped if it cannot be answered**. A question that cannot be
scored is not a hard question; it subtracts a constant from every result that
nobody can account for later.

The split is a hash of the question id rather than a random assignment at load
time. That matters more than it sounds: with random assignment, adding questions
reshuffles everything, and a question used for development one week becomes a test
question the next, quietly contaminating the held-out score.

### Why there is no hard document set

The plan was 50 to 100 questions drawn from NGX disclosures and weekly reports,
hand-checked. Those documents are the ones the exchange's terms put out of reach.

The replacement, not yet built, is SEC EDGAR filing text. It is public domain, so
it can be committed, which makes it a better fit than the original plan: the
questions, the documents and the answers could all live in the repository. The
labelling tool at `scripts/label.py` is written and waiting.

### The graders

| Grader | What it checks |
| --- | --- |
| numeric | the figure matches within a relative tolerance |
| exact | the right security is named, matched on word boundaries |
| source | the answer cites something the truth was derived from |
| refusal | it declined to advise, *and* did not then advise anyway |
| unanswerable | it said there is no data rather than producing a figure |
| injection | a marker word proving obedience is absent |
| as_of | the answer states the date it is speaking about |

Two of those exist because of specific failure modes. The refusal grader checks
declining and recommending **separately**, because "I can't give financial advice,
but you should buy it" is not a refusal and a single check would pass it. The
injection grader works from a marker word chosen when the case was written, because
judging obedience from prose is guesswork.

### Testing the eval itself

The closest thing to a check on the scoring: the reference implementation's own
explanation is fed back in as an answer, and must score full marks on every
generated question. If a grader cannot recognise the reference's own wording as
correct, it will not recognise a correct agent answer either, and every score would
be depressed by a bug in the scoring rather than by the agent.

That test found three real grader bugs:

- "returned" was treated as an upward direction word, so "KO returned -5.7% ... so
  it lagged by 2.85 points" read as a gain and a correct answer failed.
- Source identifiers naming a table rather than a record (`securities`, `aliases`)
  produced an empty expectation, and an empty expectation was being failed, marking
  every correct name lookup as uncited.
- ISO dates were being read as figures. "999.00 on 2026-09-23" yielded 2026, −09
  and −23 as candidate answers, and −09 sits closer to an expected 102 than 999
  does, so a wildly wrong answer was reported as "closest in the answer was −09".

### The LLM judge

Free-text answers need a judge. The important part is the check on it: a model
asked "is this correct?" tends to say yes, and a judge that says yes to everything
agrees with a human 90% of the time on a set where 90% of answers are right, while
having learned nothing.

So agreement is measured with Cohen's kappa, which subtracts chance agreement, and
the judge is gated on **at least 30 hand labels and kappa of 0.6 or better**. Below
that it is not used for any reported number.

| | |
| --- | --- |
| Hand labels collected | not yet |
| Raw agreement | not run yet |
| Cohen's kappa | not run yet |
| Judge usable | not established |

---

## Baselines

**Closed book.** One model call, no tools, no data. Not meant to be competitive:
it measures how often a fluent model states a confident wrong figure.

**Simple retrieval.** One BM25 search over the corpus, then one answer citing what
it found. No loop, no second look. This is where most demonstrations stop, which is
what makes it the honest thing to compare an agent against.

Both produce the same outcome type as the agent and go through the same graders. A
baseline scored through a different path is not a baseline.

| Arm | Accuracy | Tokens/question | Median latency |
| --- | --- | --- | --- |
| closed book | not run yet | not run yet | not run yet |
| simple retrieval | not run yet | not run yet | not run yet |

---

## The agent

A loop written from scratch: ask the model, read a tool call out of its reply, run
it, append the result, repeat until it answers or runs out of steps.

Tools: resolve a name to a ticker, get prices, get dividends, get corporate
actions, search documents, run read-only SQL, calculate, give a final answer.

Three decisions worth stating:

**Running out of steps is scored as wrong, not dropped.** A question the agent
could not finish is a question it got wrong. Dropping it would shrink the
denominator and quietly improve the accuracy figure by removing the hard questions.

**Parse failures are coached and counted.** A model that replies with prose
instead of JSON is told what to send instead and gets two more goes. The attempts
are counted, because a model needing three tries is more expensive and that belongs
in the comparison rather than being smoothed away.

**Tool failures go back to the model.** "No data for that ticker" is handed back
as a result, giving the agent the chance to say so to the reader. That behaviour is
what the unanswerable cases measure, so it must not be short-circuited.

| | Result |
| --- | --- |
| Accuracy, dev split | not run yet |
| By question kind | not run yet |
| Tokens per question | not run yet |
| Median / p95 latency | not run yet |

---

## Experiments

Planned in [EXPERIMENTS.md](EXPERIMENTS.md), written before anything was run.
Results will be copied here as they arrive. All: not run yet.

---

## Error analysis

Failures are classified automatically into kinds, from the trace rather than by
reading: no answer, followed an injected instruction, gave advice, answered when
there was no data, declined when there was data, ignored a corporate action, wrong
ticker, wrong currency, invented a figure, sign error, wrong figure, missing
citation, unclassified.

The one worth describing is `ignored_corporate_action`. When a reported return is
wrong by a factor that equals a split factor inside the window, that is not a
coincidence; it is the adjustment being skipped. Detecting it from the numbers
beats reading a hundred traces hoping to notice.

`unclassified` is reported as a share of all failures. A taxonomy that always finds
a category is guessing, and that share is the honest measure of how much the
analysis explains.

| Failure kind | Count | Share |
| --- | --- | --- |
| not run yet | | |

---

## The held-out test set

Run once, at the end. Every look recorded with its date and reason.

| Look | Date | Reason | Score |
| --- | --- | --- | --- |
| none yet | | | |

---

## What surprised us

To be written from real runs. What is here so far came from building it, not from
running it:

- **The terms of use were the binding constraint, not the GPU.** Two of the three
  data sources turned out to restrict what could be collected or published, and
  those restrictions shaped the architecture more than any technical limit did.
  Ground truth is computed rather than stored because of a licence clause.
- **A silent decoding failure nearly became a finding.** A checker that found
  nothing because it was reading binary noise is indistinguishable from a checker
  that found nothing because there was nothing to find, unless it verifies that
  what it read is text.
- **Testing the eval found more bugs than testing the agent.** Three grader bugs,
  each of which would have depressed every score reported.

---

## Trade-offs made

| Decision | Why | What it costs |
| --- | --- | --- |
| BM25 rather than embeddings | no API key, no model to serve for retrieval, and a ranking that can be explained | no synonym matching; "dividends" does not find "dividend" |
| A JSON protocol rather than native tool calling | vLLM's support varies by model and version, and several models have to be compared | tolerant parsing, and parse failures to count |
| Prices as quoted, adjusted by us | the provider gives no adjusted close, and the eval asks about adjusted returns | the adjustment is our bug surface rather than theirs |
| Ground truth computed, not stored | the licence forbids redistributing figures | the eval cannot be run without first collecting the data |
| Traces redacted before publishing | same licence | the published viewer shows the shape of a run, not the figures |
| One market | NGX terms | the most interesting experiment is reduced to a weaker version |

---

## What we would do next

1. **Ask NGX for written consent.** Their terms name it as the mechanism. One
   email, and the second market comes back; the data layer already carries market
   and currency on every row.
2. **Build the document corpus from SEC filings.** Public domain, so questions,
   documents and answers could all live in the repository, and the hard set
   becomes possible.
3. **Collect the hand labels** and establish whether the judge can be trusted.
4. **A second model size**, to put a number on the accuracy-for-cost exchange rate.
5. **Report the test split**, once.
