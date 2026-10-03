# Running this

Three places things run, and they do different jobs.

| Where | What runs there | Why |
| --- | --- | --- |
| Your machine | tests, the demo, collecting data | no GPU needed, and the data has to stay off the public internet |
| Kaggle | vLLM and the evals | free GPU hours, and nothing else is free |
| GitHub Actions | tests on every push | catches a broken pipeline without a GPU |

Everything below is free. Nothing here needs a paid plan.

---

## First, on your own machine

```bash
git clone https://github.com/MelvTheGoat/Stocks.git
cd Stocks
pip install -r requirements-dev.txt
pip install -e .

python scripts/demo.py   # shows every piece working, no API key needed
pytest                   # the whole suite, no network
```

### Collect the market data

You need a free Twelve Data API key from <https://twelvedata.com/pricing>. It
takes about a minute to get and costs nothing.

```bash
export TWELVEDATA_API_KEY=your_key_here
export SEC_EMAIL=you@example.com

python scripts/collect_us.py --dry-run     # see the plan, call nothing
python scripts/collect_us.py --start 2019-01-01
python scripts/write_coverage.py           # regenerates COVERAGE.md
```

About twenty minutes for 55 securities, because the free tier allows eight
requests a minute. Safe to interrupt: run it again and it carries on from where
it stopped.

**The database is never committed.** Twelve Data licenses the data for internal
use and not for redistribution, so `data/db/` is in `.gitignore`. See
[DATA_SOURCES.md](DATA_SOURCES.md) for the clause. Anyone with their own free key
rebuilds an identical database with the command above, so every result stays
reproducible.

### Ask it something

The database is the only hard requirement; the model can be anything that speaks
the OpenAI chat API. Ollama is free, needs no GPU, and runs a 3B model on a CPU.

```bash
ollama serve                       # in one terminal
ollama pull qwen2.5:3b-instruct

python scripts/ask.py "What did AAPL close at on 2026-09-23?"
python scripts/ask.py --steps "How did Apple do against the market in 2025?"
python scripts/ask.py              # interactive, one question per line
```

A 3B model on a CPU takes a few seconds a step and will get some things wrong.
That is the point of the evals: they put a number on how wrong. For better
answers, run a 7B model on Kaggle and use `ask.py` inside the notebook.

### Freeze an eval version

```bash
python scripts/build_eval.py --version v1 --as-of 2026-09-29
```

This writes `data/eval/v1.json`, which **is** committed: it holds question text
and parameters, never answers. The correct answers are computed at run time by
reference code reading your local database.

The as-of date must be a day the database covers, and should be the day you
collected to. Once a version has been run against, do not change it: make a v2
instead, or two results stop being comparable.

---

## Then, on Kaggle

### One-time setup

1. Go to <https://www.kaggle.com> and sign in. Verify your phone number, or GPUs
   stay locked.
2. New Notebook.
3. **Settings → Accelerator → GPU T4 x2**, and **Internet → On**. Both matter: no
   accelerator means no vLLM, and no internet means it cannot clone the repo.
4. **Add-ons → Secrets.** Add each of these and tick the box to attach it to this
   notebook. A secret that exists but is not attached reads as empty, which is
   the most common way this fails.

   | Secret | What it is |
   | --- | --- |
   | `GH_TOKEN` | a GitHub fine-grained token with Contents: read and write on this repository |
   | `HF_TOKEN` | a Hugging Face token with write access, from <https://huggingface.co/settings/tokens> |
   | `HF_REPO` | your private dataset name, like `yourname/stock-agent-data` |
   | `TWELVEDATA_API_KEY` | only needed if you let Kaggle collect the data rather than doing it locally |
   | `SEC_EMAIL` | your contact address; the SEC returns 403 without one |

5. Paste the whole of [notebooks/kaggle_runner.py](notebooks/kaggle_runner.py)
   into one cell.
6. **Save & Run All.**

### Every run after that

Click **Save & Run All** again. The notebook picks the next unfinished job from
[runs/queue.yaml](runs/queue.yaml) by itself, so there is nothing to edit between
runs.

It decides what is unfinished by looking for results files on the `results`
branch. There is no status field to get out of step with reality: if a result
exists, the job is done; if it does not, the job runs again.

### What one run does

```
clone the repo
install dependencies, including vLLM
work out which job is next
fetch the database from Hugging Face, or collect it if there is none
start vLLM and wait for it
run the eval, stopping cleanly before Kaggle's limit
push results and traces to the "results" branch
upload the database and the response cache to Hugging Face
```

The response cache means a re-run costs almost nothing: a job that was
interrupted resumes, and a job repeated after a change to the grading code does
not call the model again at all.

### Reading the results

```bash
git fetch origin results
git checkout results
ls */
```

Or ask me to: say "check results" and I will fetch the branch, read the logs,
and tell you what to run next.

---

## About the GPU, honestly

T4 is a Turing card. It has 16 GB and **no bfloat16**, which is why every config
sets `dtype: float16`. A 7B model only fits with quantised weights, which is why
the configs use AWQ.

**The vLLM version is not yet settled.** vLLM's support for Turing has moved
between releases, and I could not verify from a development container which
version starts on a Kaggle T4. `VLLM_VERSION` near the top of the notebook is a
starting point, not a tested fact. The notebook prints the detected compute
capability and the installed version, and dumps vLLM's log if it exits early, so
a failure is diagnosable.

**That is what the smoke job is for.** It is five questions and a few minutes,
and its real purpose is to establish that vLLM starts, the client reaches it,
and results get pushed. If it fails, send me the printed log and I will adjust
the version.

### The budget

Kaggle gives about 30 GPU hours a week, and a session runs up to twelve hours.
Each job in the queue declares a budget in minutes and the notebook reserves 25
minutes at the end so results get pushed rather than the session being killed
mid-write. [EXPERIMENTS.md](EXPERIMENTS.md) works out how many runs fit in a week.

---

## GitHub Actions

Two workflows run on every push, and neither needs a GPU.

- **tests** — the whole suite, then again with networking disabled. The second
  pass is the proof that no test quietly depends on a live service.
- **authorship** — greps the tree and every commit message for assistant tool
  names, so that rule is a gate rather than a habit.

`tests/test_pipeline.py` is the regression eval: it builds a small database,
generates a question set, and runs all three systems through the real harness
with a scripted model. It also replays a saved response cache through the full
pipeline with a client that raises if it is called, which is how the whole chain
gets exercised on every push with no GPU and no API key.

There is a third workflow, **probe-sources**, which checks by hand which data
sources are reachable. It is run from the Actions tab when a source stops working.

---

## If something goes wrong

**"the secret X is not set"** — the secret exists but is not attached to the
notebook. Add-ons → Secrets, and tick the box next to it.

**vLLM exits while loading** — the log is printed above the error. Usually either
the model does not fit, in which case lower `max_model_len` or
`gpu_memory_utilization` in the config, or the vLLM version does not support
Turing, in which case the version needs changing.

**"The database is empty"** — collect it locally and let the notebook pull it
from Hugging Face, or set `TWELVEDATA_API_KEY` and let the notebook collect it.

**"No eval set at data/eval/v1.json"** — run `scripts/build_eval.py` locally and
merge the file it writes.

**The results push fails** — `GH_TOKEN` needs Contents: read and write on this
repository. The notebook retries four times with backoff, then leaves the files
in its own output, where they can be downloaded by hand.

**A job runs out of budget** — expected on the longer evals. The traces written
so far are kept; click Save & Run All again and it picks up where it stopped.
