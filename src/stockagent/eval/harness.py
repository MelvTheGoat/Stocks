"""Running a system over a question set and scoring it.

One function does the work, and the three systems -- agent, closed book,
retrieval -- all go through it. That is what makes their numbers comparable.

Two design points are load-bearing:

**It resumes.** A Kaggle session is killed at the time limit, and an eval over a
few hundred questions with a 7B model on a T4 does not reliably finish inside
one. Progress is kept by appending whole traces to a JSONL file; a restart reads
back which question ids are already there and skips them. Half an eval is
therefore worth something, which is the difference between making progress each
week and never finishing.

**A question that errored is scored, not dropped.** Running out of steps, failing
to produce valid JSON, a dead model connection: all of those are wrong answers as
far as a reader is concerned. Dropping them shrinks the denominator and makes a
flaky system look accurate, which is the single easiest way to publish a
misleading number in this kind of project.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from stockagent.agent.loop import AgentOutcome
from stockagent.agent.trace import TraceWriter
from stockagent.data.store import MarketStore
from stockagent.eval import reference
from stockagent.eval.graders import GraderSet, Scorecard
from stockagent.eval.schema import Question
from stockagent.eval.stats import Interval, bootstrap_interval, median, percentile


class Answerer(Protocol):
    """Anything that can answer a question. The agent and both baselines do."""

    def answer(self, question_id: str, question: str, as_of: str) -> AgentOutcome: ...


@dataclass
class QuestionResult:
    question: Question
    outcome: AgentOutcome
    scorecard: Scorecard
    # The reference explanation, kept so a failure can be read without re-running.
    expected: str = ""

    @property
    def passed(self) -> bool:
        return self.scorecard.passed

    def to_json(self) -> dict:
        return {
            "question_id": self.question.id,
            "kind": self.question.kind,
            "market": self.question.market,
            "language": self.question.language,
            "text": self.question.text,
            "passed": self.passed,
            "stop": self.outcome.stop,
            "answer": self.outcome.text(),
            "expected": self.expected,
            "failures": [
                {"grader": grade.grader, "detail": grade.detail}
                for grade in self.scorecard.failures()
            ],
            "model_calls": self.outcome.trace.model_calls,
            "tool_calls": self.outcome.trace.tool_calls,
            "total_tokens": self.outcome.trace.total_tokens,
            "latency_ms": round(self.outcome.trace.latency_ms, 2),
            "tools_used": self.outcome.trace.tools_used(),
        }


@dataclass
class EvalResults:
    """Everything one run produced."""

    run_name: str
    system: str
    eval_version: str
    split: str
    results: list[QuestionResult] = field(default_factory=list)
    skipped: int = 0
    # Questions the reference could not score at all, which is a broken question
    # rather than a wrong answer and must not be counted either way.
    unscorable: dict[str, str] = field(default_factory=dict)

    # --- headline numbers ---------------------------------------------------

    @property
    def total(self) -> int:
        return len(self.results)

    def accuracy(self, *, seed: int = 0) -> Interval:
        return bootstrap_interval([r.passed for r in self.results], seed=seed)

    def _grouped(self, key) -> dict[str, list[QuestionResult]]:
        groups: dict[str, list[QuestionResult]] = defaultdict(list)
        for result in self.results:
            groups[key(result)].append(result)
        return dict(groups)

    def by_kind(self, *, seed: int = 0) -> dict[str, Interval]:
        return {
            name: bootstrap_interval([r.passed for r in group], seed=seed)
            for name, group in sorted(self._grouped(lambda r: r.question.kind).items())
        }

    def by_market(self, *, seed: int = 0) -> dict[str, Interval]:
        return {
            name: bootstrap_interval([r.passed for r in group], seed=seed)
            for name, group in sorted(self._grouped(lambda r: r.question.market).items())
        }

    def by_language(self, *, seed: int = 0) -> dict[str, Interval]:
        return {
            name: bootstrap_interval([r.passed for r in group], seed=seed)
            for name, group in sorted(self._grouped(lambda r: r.question.language).items())
        }

    # --- what it cost ------------------------------------------------------

    def tokens_per_question(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.outcome.trace.total_tokens for r in self.results) / len(self.results)

    def latency(self) -> dict[str, float]:
        """Median and 95th percentile, in milliseconds.

        A mean would be dominated by the few questions where the agent took eight
        steps, and would describe no actual question.
        """
        values = [r.outcome.trace.latency_ms for r in self.results]
        return {"median_ms": round(median(values), 2), "p95_ms": round(percentile(values, 0.95), 2)}

    def stops(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for result in self.results:
            counts[result.outcome.stop] += 1
        return dict(sorted(counts.items()))

    # --- reporting ---------------------------------------------------------

    def summary(self) -> str:
        accuracy = self.accuracy()
        lines = [
            f"{self.system} on {self.eval_version} ({self.split}): "
            f"{accuracy.as_percent()} over {self.total} questions",
            f"  tokens per question: {self.tokens_per_question():.0f}",
            f"  latency: median {self.latency()['median_ms']:.0f}ms, "
            f"p95 {self.latency()['p95_ms']:.0f}ms",
            f"  how runs ended: {self.stops()}",
        ]
        if self.skipped:
            lines.append(f"  skipped (already traced): {self.skipped}")
        if self.unscorable:
            lines.append(f"  unscorable questions: {len(self.unscorable)}")
        return "\n".join(lines)

    def to_json(self) -> dict:
        return {
            "run": self.run_name,
            "system": self.system,
            "eval_version": self.eval_version,
            "split": self.split,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total": self.total,
            "accuracy": {
                "point": self.accuracy().point,
                "low": self.accuracy().low,
                "high": self.accuracy().high,
            },
            "by_kind": {
                name: {"point": i.point, "low": i.low, "high": i.high, "n": i.n}
                for name, i in self.by_kind().items()
            },
            "by_market": {
                name: {"point": i.point, "low": i.low, "high": i.high, "n": i.n}
                for name, i in self.by_market().items()
            },
            "by_language": {
                name: {"point": i.point, "low": i.low, "high": i.high, "n": i.n}
                for name, i in self.by_language().items()
            },
            "tokens_per_question": round(self.tokens_per_question(), 1),
            "latency": self.latency(),
            "stops": self.stops(),
            "skipped": self.skipped,
            "unscorable": self.unscorable,
            "questions": [result.to_json() for result in self.results],
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2) + "\n")
        return path


def run_eval(
    system: Answerer,
    questions: Sequence[Question],
    store: MarketStore,
    *,
    system_name: str,
    eval_version: str,
    split: str = "dev",
    run_name: str = "",
    graders: GraderSet | None = None,
    traces: TraceWriter | None = None,
    resume: bool = True,
    progress: bool = False,
) -> EvalResults:
    """Ask every question, score every answer, keep every trace."""
    graders = graders or GraderSet()
    results = EvalResults(
        run_name=run_name or system_name,
        system=system_name,
        eval_version=eval_version,
        split=split,
    )

    already = traces.completed_ids() if (traces and resume) else set()

    for position, question in enumerate(questions, start=1):
        if question.id in already:
            results.skipped += 1
            continue

        try:
            truth = reference.answer(store, question)
        except reference.ReferenceError as error:
            # A broken question, not a wrong answer. Counting it either way would
            # misstate the result, so it is recorded and set aside.
            results.unscorable[question.id] = str(error)
            continue

        outcome = system.answer(question.id, question.text, question.as_of.isoformat())
        scorecard = graders.grade(question, truth, outcome.text())
        results.results.append(
            QuestionResult(
                question=question,
                outcome=outcome,
                scorecard=scorecard,
                expected=truth.explanation,
            )
        )

        if traces is not None:
            # Written as we go, so a session killed at the time limit keeps
            # everything answered so far.
            traces.write(outcome.trace)

        if progress:
            mark = "ok  " if scorecard.passed else "FAIL"
            print(f"  {position:>4}/{len(questions)} {mark} {question.id} ({question.kind})")

    return results


def compare(left: EvalResults, right: EvalResults) -> str:
    """Two results side by side, with the honest reading of the difference."""
    a, b = left.accuracy(), right.accuracy()
    gap = (b.point - a.point) * 100
    verdict = (
        "the intervals overlap, so this difference is not established"
        if a.overlaps(b)
        else "the intervals do not overlap"
    )
    return (
        f"{left.system}: {a.as_percent()} over {a.n}\n"
        f"{right.system}: {b.as_percent()} over {b.n}\n"
        f"difference: {gap:+.1f} points - {verdict}"
    )


def failures_by_kind(results: EvalResults) -> dict[str, list[QuestionResult]]:
    """Failed questions grouped by kind, the starting point for Phase 9."""
    grouped: dict[str, list[QuestionResult]] = defaultdict(list)
    for result in results.results:
        if not result.passed:
            grouped[result.question.kind].append(result)
    return dict(sorted(grouped.items()))


def all_failures(results: Iterable[EvalResults]) -> list[QuestionResult]:
    return [r for result in results for r in result.results if not r.passed]
