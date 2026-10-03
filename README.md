# Stock question answering, and the eval that measures it

An agent that answers factual questions about US stock prices, dividends and
corporate actions, and the evaluation system that shows how well it actually works.

An "agent" here means a program that runs a language model in a loop, lets it call
tools such as a price lookup or a calculator, and stops when it has an answer.
"Eval" is short for evaluation: a fixed set of questions with known correct
answers, used to score the agent the same way every time.

**This is not financial advice.** The agent reports figures and cites where they
came from. Asked whether to buy something, it declines and offers the figures
instead.

## Why this project

Most portfolio projects that use language models show a handful of good examples.
That proves very little. A model can sound completely certain and still invent a
share price, and nothing in the answer tells you which time this is.

So this is built the other way round. The eval set, the reference answers and the
graders came first; the agent came second. Every number in the write-up points at a
run log, and anything not yet run says "not run yet" rather than showing a
placeholder.

The most useful thing in here may be the write-up of what went wrong:
[REPORT.md](REPORT.md) records three grader bugs that would each have depressed
every score, and a decoding failure that nearly became a finding about what a
website's terms permit.

## Status

**Everything is built. Nothing has been run on a GPU yet.**

| Part | State |
| --- | --- |
| Repo, config, model client, CI | done |
| Data layer: records, store, trading calendar, cross-check, returns | done |
| US collector (Twelve Data, SEC) | done, needs a free API key to run |
| Eval set, reference answers, graders, LLM judge | done |
| Baselines: closed book, simple retrieval | done |
| Agent: loop, seven tools, traces | done |
| Kaggle runner, job queue | done, awaiting a first run |
| Error analysis, trace viewer | done |
| **Results** | **not run yet** |

619 tests, passing with networking disabled.

## Seeing it work, without any setup

```bash
git clone https://github.com/MelvTheGoat/Stocks.git
cd Stocks
pip install -r requirements-dev.txt
pip install -e .

python scripts/demo.py   # every piece, explained as it runs
pytest                   # the whole suite
```

`scripts/demo.py` works from sample responses saved in the repository. No API key,
no network, same output on any machine. It reads real saved market data, stores it,
queries it with SQL, catches a planted bad price by comparing two sources, and
answers a question about a day the market was shut.

## Actually using it

Once the database exists, ask it questions:

```bash
# a model, free and with no GPU needed
ollama serve
ollama pull qwen2.5:3b-instruct

python scripts/ask.py "What did AAPL close at on 2026-09-23?"
python scripts/ask.py --steps "Did AAPL beat SPY in 2025?"
python scripts/ask.py            # interactive
```

`--steps` shows which tools it called and why, how many tokens it spent, and how
long it took.

Any OpenAI-compatible endpoint works: `--endpoint` and `--model` point it
elsewhere. Ollama is the default because it is free and runs a 3B model on a
laptop CPU.

Then, to run the evals for real: [RUNNING.md](RUNNING.md).

## How it fits together

```
configs/            one YAML per run; nothing else decides a result
runs/queue.yaml     the job list the Kaggle notebook works through
data/eval/          frozen question sets (questions only, never answers)
data/samples/       saved provider responses, used by the tests
notebooks/          the Kaggle runner, pasted into one cell
scripts/            ask it a question, collect, build the eval, run it, label, view
src/stockagent/
  config.py         run config, validated on load, unknown keys rejected
  llm/              model client: cache, retries, timeouts, call logging
  data/             records, parquet+DuckDB store, trading calendar, returns
  retrieval/        BM25 written from scratch, and the corpus it indexes
  tools/            the agent's seven tools
  agent/            the loop, its prompts, the JSON protocol, traces
  baselines.py      closed book and simple retrieval
  eval/             questions, reference answers, graders, judge, harness, errors
  runner/           the job queue
  viewer.py         the static trace page, with redaction
tests/              pytest; no network, no real model
```

### A few decisions worth knowing about

**Ground truth is computed, not stored.** The eval file holds question text and
parameters; the correct answers are worked out at run time by reference code
reading your own database. That started as a licence requirement and turned out to
be better design: answers cannot go stale against a corrected database.

**The dev/test split is a hash of the question id.** With random assignment,
adding questions reshuffles everything, and a question used for development one
week becomes a test question the next — quietly contaminating the held-out score.

**Running out of steps is scored as wrong, not dropped.** Dropping it would shrink
the denominator and improve the accuracy figure by removing the hard questions.

**Every reported accuracy carries a bootstrap interval.** Two overlapping
intervals are reported as "no difference established", not as a difference.

## About the Nigerian half

This was meant to cover the Nigerian Exchange as well as US stocks. Models have
read a great deal about Apple and very little about Nigerian Breweries, and that
gap separates what a model remembers from what it can work out.

**It is not in here, and the reason is the exchange's terms of use.** They prohibit
"systematic or automated data collection activities (including scraping, data
mining, data extraction and data harvesting)" without express written consent, and
separately prohibit republishing any part of the site. A daily collector committing
prices to a public branch would have done both.
[DATA_SOURCES.md](DATA_SOURCES.md) records the clauses, and the decoding bug that
briefly made those terms look permissive.

Every record in the data layer already carries a market and a currency, so Nigerian
data would slot in unchanged if consent were obtained. Until then this is a
US-market project with a documented reason for the gap, which is a more honest
result than a scraper nobody mentions.

## Documents

| File | What is in it |
| --- | --- |
| [RUNNING.md](RUNNING.md) | how to run it, on your machine and on Kaggle |
| [DATA_SOURCES.md](DATA_SOURCES.md) | every source, its terms, and the date each was checked |
| [COVERAGE.md](COVERAGE.md) | what the database actually holds; generated, not written |
| [EXPERIMENTS.md](EXPERIMENTS.md) | what will be run and what each experiment settles |
| [REPORT.md](REPORT.md) | the write-up, with every result marked not run yet |

## Reproducing it

Everything is free. No paid APIs, no paid services, no paid data.

1. Clone it and run the tests.
2. Get a free Twelve Data API key and run `scripts/collect_us.py`. About twenty
   minutes, resumable.
3. `scripts/build_eval.py` to freeze a question set.
4. Follow [RUNNING.md](RUNNING.md) for the Kaggle side.

The market data is not in this repository: Twelve Data licenses it for internal use
and not for redistribution, so `data/db/` is gitignored. The collector is here
instead, and it rebuilds an identical database from your own key, so every number
regenerates.
