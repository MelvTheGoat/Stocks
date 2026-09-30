# Stock question answering, and the eval that measures it

An agent that answers factual questions about US stocks and Nigerian stocks
listed on the Nigerian Exchange (NGX), and the evaluation system that shows how
well it actually works.

An "agent" here means a program that runs a language model in a loop, lets it
call tools such as a price lookup or a calculator, and stops when it has an
answer. "Eval" is short for evaluation: a fixed set of questions with known
correct answers, used to score the agent the same way every time.

**This is not financial advice.** The agent reports figures and cites where they
came from. It will not tell anyone what to buy.

## Why this project

Most portfolio projects that use language models show a handful of good
examples. That proves very little. A model can look fluent and still invent a
share price. This project is built the other way round: the eval set and the
graders come first, the agent comes second, and every claim in the write-up
points at a run log.

There is a second reason for choosing Nigerian stocks alongside US ones. Large
models have read a great deal about Apple and very little about Nigerian
Breweries. That gap is the interesting part. It lets us measure how much of a
model's apparent skill is memory rather than reasoning, and whether giving it
real data closes the gap.

## Status

Early. Nothing has been run on a GPU yet.

| Part | State |
| --- | --- |
| Repo, config, model client, CI | done |
| Data layer: records, store, trading calendar, cross-check | done |
| US universe (54 companies plus SPY) | defined, no prices collected yet |
| NGX daily price collector | **abandoned — their terms forbid it** |
| Eval set | not started |
| Kaggle runner | not started |
| Baselines | not run yet |
| Agent | not started |
| Experiments | not run yet |

Results tables will appear here once real runs exist. Until then this file says
"not run yet" rather than showing a placeholder number.

### About the Nigerian half

The plan was to build our own NGX price history, since the full history is sold
rather than published. That is not going to happen by collecting it.

NGX's terms of use prohibit "systematic or automated data collection
activities (including scraping, data mining, data extraction and data
harvesting)" without their express written consent, and separately prohibit
republishing any part of the site. A daily collector committing prices to a
public branch would have done both. So it was not built.
[DATA_SOURCES.md](DATA_SOURCES.md) records the clauses, and also records the
decoding bug that briefly made those terms look permissive.

Everything in the data layer already carries a market and a currency on every
row, so Nigerian data would slot in unchanged if written consent is ever
obtained. Until then this is a US-market project with a documented reason for
the gap, which is a more honest result than a scraper nobody mentions.

## Repository layout

See [ARCHITECTURE.md](ARCHITECTURE.md) once it exists. For now:

```
configs/            one YAML file per run, so any result can be re-run exactly
runs/               the job queue the Kaggle notebook reads
src/stockagent/     the package
  config.py         run configuration, validated on load
  llm/              model client: cache, retries, timeouts, call logging
  collectors/       scheduled data collection (NGX daily prices)
tests/              pytest suite; never calls a real model
data/samples/       small fixture files used by tests
```

## Seeing it work

```bash
pip install -r requirements-dev.txt
pip install -e .

python scripts/demo.py   # runs every piece built so far and explains itself
pytest                   # the full test suite
```

`scripts/demo.py` works from sample responses saved in the repository, so it
needs no API key, reaches no network, and prints the same thing on any machine.
It reads real saved market data, stores it, queries it with SQL, catches a
planted bad price by comparing two sources, and answers a question about a day
the market was shut.

Tests never reach the network and never call a real model. They use a fake
model client that returns scripted replies. `pytest --disable-socket` passes
too, which is the proof rather than the promise.

There is no web page to look at yet. The trace viewer, where you can click
through what the agent did on each question, arrives with the agent itself.

## Data sources

Every source, and its terms of use, is recorded in
[DATA_SOURCES.md](DATA_SOURCES.md).
