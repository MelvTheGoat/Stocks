"""Hand-check answers, one at a time, and record the verdicts.

Shows a question, what the reference says, and the answer a system gave, then
waits for a verdict. Written as a command-line tool rather than a web page
because it has to be resumable and has to work wherever the database is, and a
page would mean shuttling a file back and forth.

Every verdict is written to disk as it is given, so stopping halfway costs
nothing. Re-running skips what is already labelled.

The labels are what the LLM judge is measured against. Thirty of them is the
minimum before the judge can be trusted at all, so the tool reports how many
there are each time it starts.

Usage:
    python scripts/label.py --questions data/eval/v1.json --split hard
    python scripts/label.py --questions data/eval/v1.json --results runs/output/agent.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stockagent.data.store import MarketStore
from stockagent.eval import reference
from stockagent.eval.dataset import EvalSet
from stockagent.eval.schema import Question

DATABASE = Path("data/db")

KEYS = """
  y  the answer is correct
  n  the answer is wrong
  s  skip for now
  ?  show the question's notes and parameters again
  q  save and quit
"""


def load_labels(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_labels(path: Path, labels: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(labels, indent=2, sort_keys=True) + "\n")


def answers_from_results(path: Path | None) -> dict[str, str]:
    """Answers keyed by question id, read from a run's results file."""
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text())
    return {row["question_id"]: row.get("answer", "") for row in payload.get("questions", [])}


def describe(question: Question, expected: str, candidate: str) -> str:
    lines = [
        "=" * 76,
        f"{question.id}   [{question.kind}, {question.market}, {question.language}]",
        "=" * 76,
        "",
        f"QUESTION   {question.text}",
        f"AS OF      {question.as_of.isoformat()}",
    ]
    if question.params.tickers:
        lines.append(f"TICKERS    {', '.join(question.params.tickers)}")
    if question.params.start or question.params.end:
        lines.append(f"WINDOW     {question.params.start} to {question.params.end}")
    if question.notes:
        lines.append(f"NOTES      {question.notes}")
    lines += [
        "",
        "REFERENCE  " + (expected or "(none; this question is answered by hand)"),
        "",
        "ANSWER     " + (candidate or "(no answer recorded for this question)"),
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--labels", type=Path, help="defaults to <questions>-labels.json")
    parser.add_argument("--results", type=Path, help="a run's results file, for its answers")
    parser.add_argument("--split", choices=["dev", "test", "hard", "all"], default="all")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--relabel", action="store_true", help="revisit questions already labelled")
    args = parser.parse_args(argv)

    labels_path = args.labels or args.questions.with_name(f"{args.questions.stem}-labels.json")

    eval_set = EvalSet.load(args.questions)
    questions = eval_set.questions if args.split == "all" else eval_set.split(args.split)
    labels = load_labels(labels_path)
    answers = answers_from_results(args.results)

    todo = [q for q in questions if args.relabel or q.id not in labels]
    if args.limit:
        todo = todo[: args.limit]

    print(f"{eval_set.summary()}")
    print(f"labels so far: {len(labels)} in {labels_path}")
    print(f"to label now:  {len(todo)}")
    if len(labels) < 30:
        print(
            f"note: the LLM judge needs at least 30 hand labels before it can be "
            f"trusted. You have {len(labels)}."
        )
    if not todo:
        print("\nNothing to do.")
        return 0
    print(KEYS)

    store = MarketStore(DATABASE)

    for position, question in enumerate(todo, start=1):
        try:
            truth = reference.answer(store, question)
            expected = truth.explanation
        except reference.ReferenceError:
            expected = ""

        print(f"\n[{position}/{len(todo)}]")
        print(describe(question, expected, answers.get(question.id, "")))

        while True:
            try:
                key = input("verdict (y/n/s/?/q): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nsaving and stopping.")
                save_labels(labels_path, labels)
                return 0

            if key == "?":
                print(describe(question, expected, answers.get(question.id, "")))
                continue
            if key == "q":
                save_labels(labels_path, labels)
                print(f"saved {len(labels)} labels to {labels_path}")
                return 0
            if key == "s":
                break
            if key in ("y", "n"):
                note = input("note (optional): ").strip()
                labels[question.id] = {"correct": key == "y", "note": note}
                # Written now, not at the end, so stopping costs nothing.
                save_labels(labels_path, labels)
                break
            print(f"not a verdict. {KEYS}")

    save_labels(labels_path, labels)
    correct = sum(1 for row in labels.values() if row["correct"])
    print(f"\nsaved {len(labels)} labels to {labels_path} ({correct} correct)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
