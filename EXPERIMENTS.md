# Experiments

What will be run, in what order, and what each one is supposed to settle.

Written before anything was run, deliberately. Deciding afterwards which
comparisons to report is how a project ends up with six impressive numbers and no
honest account of what was tried.

**Nothing in this file has been run yet.** Every result table says "not run yet"
and will keep saying so until a real Kaggle run fills it in.

---

## The budget

Kaggle gives roughly **30 GPU hours a week**, in sessions of up to twelve hours.
That is the whole constraint, and it decides how many experiments are possible.

The arithmetic, once the cost of one run is known:

```
runs per week = 30 hours / (hours per dev-set run)
```

**Hours per dev-set run: not measured yet.** It cannot be guessed usefully,
because it depends on how many steps the agent takes per question, and that is one
of the things being measured. The smoke job and then `agent-dev` will establish
it.

A rough expectation, to be replaced by a measurement: the dev split is about 120
questions, an agent run takes perhaps 4 to 8 model calls per question, and a 7B
AWQ model on a T4 generates slowly. If that comes to around 20 seconds a question,
a dev run is about 40 minutes and 30 hours buys roughly 45 runs a week. If it is
nearer 60 seconds, a dev run is two hours and the week buys 15. The queue in
[runs/queue.yaml](runs/queue.yaml) has eight jobs, so either way the first full
pass fits comfortably inside one week.

Two things cut the cost substantially:

- **The response cache.** Re-running an eval after changing only the grading code
  costs no GPU time at all, because every model call is served from disk. This is
  why experiments that only change scoring are nearly free.
- **Resuming.** A job killed at the session limit keeps its traces, so a long run
  spread over two sessions costs the same as one long session.

### Where the budget goes

| Phase | Jobs | Notes |
| --- | --- | --- |
| Getting it working | smoke | minutes, and it has to pass before anything else |
| Baselines | closed-book-dev, retrieval-dev | the numbers the agent must beat |
| The agent | agent-dev | Experiment A |
| Tool design | agent-purpose-built-dev, agent-sql-only-dev | Experiment B |
| Self-checking | agent-self-check-dev | Experiment D |
| Noise | agent-dev-repeat | how big a difference has to be to mean anything |
| Model size | a second model, configs not yet written | Experiment C |
| Held-out | the test split, once, at the end | Experiment G |

---

## A. The agent against both baselines

**Question.** Does a tool-using loop beat answering from memory, and does it beat
one retrieval call?

**Arms.** `closed-book-dev`, `retrieval-dev`, `agent-dev`. Same eval version, same
split, same model, same graders.

**Reported.** Accuracy with a bootstrap interval, broken down by question kind.
Tokens per question and latency for each arm.

**What would make it interesting.** The closed-book number is the one worth
reading carefully. It measures how often a model states a confident wrong figure
with no data in front of it. If that number is high, the case for grounding is
made by the baseline rather than argued for.

| Arm | Accuracy | Tokens/question | Median latency |
| --- | --- | --- | --- |
| closed book | not run yet | not run yet | not run yet |
| simple retrieval | not run yet | not run yet | not run yet |
| agent | not run yet | not run yet | not run yet |

---

## B. Tool design

**Question.** Do purpose-built tools beat letting the model write SQL?

**Arms.** `agent-dev` (everything), `agent-purpose-built-dev` (lookups and a
calculator, no SQL, no search), `agent-sql-only-dev` (SQL and a calculator).

**Why it is worth asking.** Purpose-built tools encode knowledge the model then
does not need: `get_corporate_actions` explains what a split factor means, and
`get_prices` says which trading day it substituted for a Sunday. SQL encodes none
of that, so the model has to know to look. The prediction is that SQL does better
on questions needing an unusual aggregation and worse on anything involving a
corporate action. If that is what happens, it is an argument for tools that carry
domain knowledge rather than tools that carry power.

| Arm | Accuracy | Tokens/question | Worst question kind |
| --- | --- | --- | --- |
| all tools | not run yet | not run yet | not run yet |
| purpose-built only | not run yet | not run yet | not run yet |
| SQL only | not run yet | not run yet | not run yet |

---

## C. Model size

**Question.** What does a smaller model cost in accuracy, and what does it save
in time and tokens?

**Arms.** The 7B AWQ model from the configs, and a smaller one (3B class) at the
same settings. Configs not yet written: the second model is chosen once the first
has actually started on a T4, since that settles what the GPU will take.

**Reported.** Accuracy, tokens per question, GPU-seconds per question, median and
95th-percentile latency. The interesting output is not which is better but what
the exchange rate is.

| Model | Accuracy | Tokens/question | GPU-seconds/question |
| --- | --- | --- | --- |
| 7B AWQ | not run yet | not run yet | not run yet |
| 3B class | not run yet | not run yet | not run yet |

---

## D. Does self-checking pay for itself?

**Question.** An extra pass telling the agent to verify its own figures before
answering. Worth the tokens?

**Arms.** `agent-dev` against `agent-self-check-dev`.

**How it will be judged.** Accuracy alone is not the answer. A pass that buys two
points for 60% more tokens is a bad trade at this budget, and the write-up should
say so rather than reporting the accuracy gain and stopping. The cost columns are
the point of this experiment.

| Arm | Accuracy | Tokens/question | Median latency |
| --- | --- | --- | --- |
| agent | not run yet | not run yet | not run yet |
| agent with self-check | not run yet | not run yet | not run yet |

---

## E. Robustness

**Question.** Does the agent hold up on the cases designed to break it?

**Cases.** All already in the eval set:

- **Prompt injection.** Five documents with instructions planted in them. Scored
  by whether a marker word appears, so a pass cannot be faked by hedging.
- **Unanswerable.** Six questions with no answer in the data, including future
  dates and a company we deliberately do not cover. Saying so is correct.
- **Advice.** Seven requests for a recommendation. A pass means declining *and*
  not recommending anyway, which are scored separately on purpose.
- **Pidgin.** Six questions in Nigerian Pidgin, paired with plain-English
  equivalents elsewhere in the set.

**Reported.** Accuracy on each group, for every arm. The injection and advice
numbers are reported for the baselines too: a system with no tools cannot follow a
retrieved instruction, so a low injection score for the agent would be a cost of
giving it retrieval and should be stated as such.

| Group | Closed book | Retrieval | Agent |
| --- | --- | --- | --- |
| injection | not run yet | not run yet | not run yet |
| unanswerable | not run yet | not run yet | not run yet |
| advice | not run yet | not run yet | not run yet |
| Pidgin vs English | not run yet | not run yet | not run yet |

---

## F. The memory gap

**Question.** How much of a model's apparent skill is memory rather than
reasoning?

**This is the experiment the project was designed around, and it has been cut
down.** The plan was to compare US stocks, which models have read a great deal
about, against Nigerian ones, which they have not. NGX data was ruled out: the
exchange's terms prohibit automated collection without written consent. See
[DATA_SOURCES.md](DATA_SOURCES.md).

What can still be measured on US data alone:

- **Closed book against grounded, per question kind.** Where the closed-book
  baseline does well, memory is carrying it. Where it collapses, the data is. That
  is a weaker version of the same question and it does not need a second market.
- **Closed book by company.** The universe spans mega-caps and less-covered
  names. If closed-book accuracy tracks how much has been written about a company,
  that is the memory effect showing up within one market.
- **Closed book on dates.** A model may remember roughly what Apple is worth and
  have no idea what it closed at on a particular Tuesday. Splitting the
  closed-book result by question kind should show that sharply.

The two-market comparison stays in the write-up as a stated limitation with the
reason, not as an unexplained gap. If written consent is ever obtained, the data
layer already carries `market` and `currency` on every row and the experiment runs
unchanged.

| Measure | Result |
| --- | --- |
| closed book by question kind | not run yet |
| closed book vs agent, by kind | not run yet |
| NGX comparison | not possible; see DATA_SOURCES.md |

---

## G. The held-out test set

Run **once**, at the very end, after every decision has been made on the dev
split. A third of the generated questions, held back by a hash of the question id
so the split never shifts when questions are added.

Every look at it will be recorded here with the date and the reason. If the test
score is much worse than the dev score, that is the dev split having been fitted,
and the write-up says so.

| Look | Date | Reason | Score |
| --- | --- | --- | --- |
| none yet | | | |

---

## How noise is handled

`agent-dev-repeat` is the same job as `agent-dev` with a different sampling seed.
The gap between those two is run-to-run variation, and it is the bar any other
difference has to clear before it means anything.

Sampling is greedy (`temperature: 0.0`) everywhere, so the variation should be
small, but "should be" is not a measurement. Key comparisons get a repeat run.

Every reported accuracy carries a bootstrap interval. Two overlapping intervals
are reported as "no difference established", not as a difference, however
suggestive the point estimates look.
