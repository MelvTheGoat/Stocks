"""Ask the agent a question from the command line.

This is the thing to use once the database exists. It runs the same agent the
evals score, against the same database, and prints what it did.

It needs a model behind an OpenAI-compatible endpoint. Two free ways to get one:

**Ollama, on your own machine.** No GPU needed; a 3B model runs on a laptop CPU.

    ollama serve
    ollama pull qwen2.5:3b-instruct
    python scripts/ask.py --endpoint http://localhost:11434/v1 \\
        --model qwen2.5:3b-instruct "What did AAPL close at on 2026-09-23?"

**vLLM, in a Kaggle notebook.** Faster and bigger, but a Kaggle session is not
reachable from your machine, so this is for running inside the notebook itself.

Examples:

    python scripts/ask.py "What did AAPL close at on 2026-09-23?"
    python scripts/ask.py --steps "Did AAPL beat SPY in 2025?"
    python scripts/ask.py            # interactive, one question per line
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from stockagent.agent.loop import Agent
from stockagent.config import ModelConfig
from stockagent.data.store import MarketStore
from stockagent.llm import build_client
from stockagent.llm.base import ModelError
from stockagent.llm.openai_client import OpenAICompatibleClient
from stockagent.retrieval.corpus import build_index
from stockagent.tools import build_tools

DATABASE = Path("data/db")
CACHE = Path(".cache/responses")

BANNER = """\
Ask about US stock prices, dividends and corporate actions.

It answers only from the database, cites what it read, and says so when the data
does not cover something. It will not tell you whether to buy anything.

Type a question, or 'quit' to stop.
"""


def latest_day(store: MarketStore) -> date:
    rows = store.query("SELECT max(day) FROM bars WHERE market = 'US'")
    return rows[0][0] if rows and rows[0][0] else date.today() - timedelta(days=1)


def show(outcome, *, steps: bool) -> None:
    if steps:
        print()
        for step in outcome.trace.steps:
            if step.kind == "tool":
                mark = "ok" if step.detail.get("ok") else "failed"
                print(f"  -> {step.detail.get('tool')} ({mark})")
                thought = step.detail.get("thought")
                if thought:
                    print(f"     because: {thought}")
            elif step.kind == "error":
                print(f"  !! {step.detail.get('problem')}: {step.detail.get('reason', '')}")

    print()
    if not outcome.answered:
        print(f"No answer: the run ended as {outcome.stop}.")
        if outcome.detail:
            print(f"  {outcome.detail}")
        return

    print(outcome.answer.text.strip())
    if outcome.answer.as_of:
        print(f"\nAs of {outcome.answer.as_of}.")
    if outcome.answer.sources:
        print(f"Read: {', '.join(outcome.answer.sources)}")
    if steps:
        trace = outcome.trace
        print(
            f"\n({trace.model_calls} model calls, {trace.tool_calls} tool calls, "
            f"{trace.total_tokens} tokens, {trace.latency_ms / 1000:.1f}s)"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("question", nargs="*", help="the question; omit for interactive mode")
    parser.add_argument("--endpoint", default="http://localhost:11434/v1",
                        help="an OpenAI-compatible endpoint (default: Ollama)")
    parser.add_argument("--model", default="qwen2.5:3b-instruct")
    parser.add_argument("--as-of", type=date.fromisoformat,
                        help="the date to treat as today; defaults to the last day held")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--tools", default="full", help="full, purpose_built, sql_only")
    parser.add_argument("--steps", action="store_true", help="show what the agent did")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)

    store = MarketStore(DATABASE)
    if not store.query("SELECT count(*) FROM bars")[0][0]:
        print("The database is empty. Collect it first:")
        print("  export TWELVEDATA_API_KEY=...")
        print("  python scripts/collect_us.py --start 2019-01-01")
        return 1

    probe = OpenAICompatibleClient(base_url=args.endpoint, timeout_s=5.0)
    if not probe.is_ready():
        print(f"Nothing is answering at {args.endpoint}.")
        print("\nStart a model. The free option that needs no GPU:")
        print("  ollama serve")
        print(f"  ollama pull {args.model}")
        print("\nOr point --endpoint at something else that speaks the OpenAI chat API.")
        return 1

    as_of = args.as_of or latest_day(store)
    client = build_client(
        _model_config(args),
        cache_dir=None if args.no_cache else CACHE,
        log_path=Path("runs/output/ask-calls.jsonl"),
        run_name="ask",
    )
    agent = Agent(
        client=client,
        registry=build_tools(store, index=build_index(store, "US"), names=args.tools),
        model=args.model,
        max_steps=args.max_steps,
        max_tokens=700,
        run_name="ask",
    )

    if args.question:
        return _ask_one(agent, " ".join(args.question), as_of, steps=args.steps)

    print(BANNER)
    print(f"The database runs to {as_of}, so that is being treated as today.\n")
    number = 0
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            return 0
        number += 1
        _ask_one(agent, question, as_of, steps=args.steps, label=f"q{number}")


def _ask_one(agent: Agent, question: str, as_of: date, *, steps: bool, label: str = "q1") -> int:
    try:
        outcome = agent.answer(label, question, as_of.isoformat())
    except ModelError as error:
        print(f"\nThe model could not be reached: {error}")
        return 1
    show(outcome, steps=steps)
    print()
    return 0 if outcome.answered else 1


def _model_config(args) -> ModelConfig:
    return ModelConfig(
        name=args.model,
        endpoint=args.endpoint,
        temperature=0.0,
        max_tokens=700,
        timeout_s=180.0,
    )


if __name__ == "__main__":
    sys.exit(main())
