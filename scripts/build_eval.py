"""Generate and freeze a version of the eval set.

Run after a collection, once, per version. The file it writes is committed: it
holds question text and parameters, never answers, so the provider's data stays
out of the repository while the questions stay reproducible.

Usage:
    python scripts/build_eval.py --version v1 --as-of 2026-09-29
    python scripts/build_eval.py --version v1 --as-of 2026-09-29 --force
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from stockagent.data.store import MarketStore
from stockagent.eval.dataset import EvalSet, split_counts
from stockagent.eval.generate import build_question_set

DATABASE = Path("data/db")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="a name like v1; becomes the filename")
    parser.add_argument("--as-of", required=True, type=date.fromisoformat)
    parser.add_argument("--market", default="US", choices=["US", "NGX"])
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--force", action="store_true", help="overwrite an existing version")
    args = parser.parse_args(argv)

    path = EvalSet.path_for(args.version)
    if path.exists() and not args.force:
        # A frozen version must not change under results that already cite it.
        print(f"{path} already exists. A version is frozen once published: pick a new")
        print("version name, or pass --force if nothing has been run against it yet.")
        return 1

    store = MarketStore(DATABASE)
    if not store.query("SELECT count(*) FROM bars")[0][0]:
        print("The database is empty. Run scripts/collect_us.py first.")
        return 1

    report = build_question_set(
        store,
        as_of=args.as_of,
        market=args.market,
        benchmark=args.benchmark,
        seed=args.seed,
    )

    eval_set = EvalSet(
        version=args.version,
        as_of=args.as_of,
        questions=report.kept,
        notes=(
            f"generated from the database with seed {args.seed}; "
            f"{len(report.dropped)} proposed questions dropped as unanswerable"
        ),
    )
    eval_set.check()
    eval_set.save(path)

    print(eval_set.summary())
    print(f"by kind:   {eval_set.by_kind()}")
    print(f"by split:  {split_counts(eval_set.questions)}")
    if report.dropped:
        print(f"\ndropped {len(report.dropped)} proposed questions. First few:")
        for question_id, reason in list(report.dropped.items())[:5]:
            print(f"  {question_id}: {reason}")
    print(f"\nwrote {path}")
    print("Commit this file. It holds no market data, only questions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
