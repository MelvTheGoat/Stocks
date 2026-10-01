"""Run one system over one eval split and write the results.

Every number in the write-up comes from this. It takes a run config, so a result
can always be traced back to the exact settings that produced it.

Usage:
    python scripts/run_eval.py --config configs/smoke.yaml
    python scripts/run_eval.py --config configs/agent-dev.yaml --out runs/output
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stockagent.agent.loop import Agent
from stockagent.agent.trace import TraceWriter
from stockagent.baselines import ClosedBookBaseline, RetrievalBaseline
from stockagent.config import RunConfig
from stockagent.data.store import MarketStore
from stockagent.eval.dataset import EvalSet
from stockagent.eval.harness import run_eval
from stockagent.llm import build_client
from stockagent.retrieval.corpus import build_index
from stockagent.tools import build_tools

DATABASE = Path("data/db")
DEFAULT_OUT = Path("runs/output")
CACHE = Path(".cache/responses")


def build_system(config: RunConfig, store: MarketStore, client, run_name: str):
    """The agent or one of the baselines, as the config asks for."""
    kind = config.agent.kind

    if kind == "closed_book":
        return ClosedBookBaseline(
            client=client,
            model=config.model.name,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            seed=config.model.seed,
            run_name=run_name,
        )

    if kind == "retrieval":
        return RetrievalBaseline(
            client=client,
            model=config.model.name,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            seed=config.model.seed,
            run_name=run_name,
            index=build_index(store, config.eval.markets[0]),
        )

    tool_names = config.agent.tools or "full"
    index = build_index(store, config.eval.markets[0])
    return Agent(
        client=client,
        registry=build_tools(store, index=index, names=tool_names),
        model=config.model.name,
        max_steps=config.agent.max_steps,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
        seed=config.model.seed,
        self_check=config.agent.self_check,
        run_name=run_name,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-cache", action="store_true", help="call the model even when cached")
    parser.add_argument("--no-resume", action="store_true", help="re-ask questions already traced")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    config = RunConfig.from_yaml(args.config)
    run_name = f"{config.name}-{config.fingerprint()}"

    eval_path = EvalSet.path_for(config.eval.version)
    if not eval_path.exists():
        print(f"No eval set at {eval_path}. Run scripts/build_eval.py first.")
        return 1
    eval_set = EvalSet.load(eval_path)

    if eval_set.as_of.isoformat() != config.eval.as_of:
        # The as-of date pins what the right answers are. A config disagreeing
        # with the set it names would score against the wrong truth.
        print(
            f"The config says as-of {config.eval.as_of} but {eval_path.name} is frozen "
            f"at {eval_set.as_of}. Fix one of them."
        )
        return 1

    questions = eval_set.split(config.eval.split)
    if config.eval.limit:
        questions = questions[: config.eval.limit]
    if not questions:
        print(f"No questions in the {config.eval.split} split.")
        return 1

    store = MarketStore(DATABASE)
    if not store.query("SELECT count(*) FROM bars")[0][0]:
        print("The database is empty. Run scripts/collect_us.py first.")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    traces = TraceWriter(args.out / f"{run_name}-traces.jsonl")

    client = build_client(
        config.model,
        cache_dir=None if args.no_cache else CACHE,
        log_path=args.out / f"{run_name}-calls.jsonl",
        run_name=run_name,
    )
    system = build_system(config, store, client, run_name)

    print(f"{run_name}: {config.agent.kind} over {len(questions)} {config.eval.split} questions")
    print(f"eval {config.eval.version} frozen at {eval_set.as_of}")

    results = run_eval(
        system,
        questions,
        store,
        system_name=config.agent.kind,
        eval_version=config.eval.version,
        split=config.eval.split,
        run_name=run_name,
        traces=traces,
        resume=not args.no_resume,
        progress=not args.quiet,
    )

    path = results.save(args.out / f"{run_name}-results.json")
    print()
    print(results.summary())
    print(f"\nwrote {path}")
    print(f"traces in {traces.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
