"""The question set on disk: versioned, split, and stable.

**Why the split matters.** Every time a result is looked at and something is
changed in response, a little information about that data leaks into the design.
Do it fifty times and the score stops measuring the system and starts measuring
how well it was fitted to those particular questions. The dev set is spent that
way on purpose. The test set is looked at a handful of times, at the end, and
every look is recorded. A test score is only worth reporting because of that
discipline, not because the questions are harder.

**Why the split is computed from the question's id.** Assigning splits randomly
at load time would reshuffle everything whenever a question was added, so a
question used for development one week could become a test question the next, and
the test score would be quietly contaminated. Here the split is a hash of the id,
so a question lands in the same place forever and adding new ones never moves the
old ones.

**Why versions are frozen.** A version pins both the questions and the as-of
date. Two numbers are comparable only if they came from the same version, so
every result records which one it used.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from stockagent.eval.schema import Question

Split = Literal["dev", "test", "hard"]

EVAL_DIR = Path("data/eval")

# Roughly a third of the generated questions are held back. Enough to measure a
# few points of difference, small enough to leave a usable dev set.
TEST_FRACTION = 0.33


def split_for(question_id: str, *, test_fraction: float = TEST_FRACTION) -> Split:
    """Which split a question belongs to, decided by its id alone.

    Stable across runs, machines and additions to the set.
    """
    digest = hashlib.sha256(question_id.encode()).hexdigest()
    # The first eight hex characters give plenty of resolution.
    position = int(digest[:8], 16) / 0xFFFFFFFF
    return "test" if position < test_fraction else "dev"


@dataclass
class EvalSet:
    """A frozen set of questions.

    `hard` questions are kept separate rather than split: they are the
    hand-labelled document questions, there are few of them, and every one is
    expensive to produce. They are reported on their own.
    """

    version: str
    as_of: date
    questions: list[Question] = field(default_factory=list)
    notes: str = ""

    def split(self, name: Split) -> list[Question]:
        if name == "hard":
            return [q for q in self.questions if q.kind == "document"]
        return [
            q
            for q in self.questions
            if q.kind != "document" and split_for(q.id) == name
        ]

    def by_kind(self) -> dict[str, int]:
        return dict(Counter(q.kind for q in self.questions))

    def by_market(self) -> dict[str, int]:
        return dict(Counter(q.market for q in self.questions))

    def summary(self) -> str:
        return (
            f"{self.version} as of {self.as_of}: {len(self.questions)} questions "
            f"({len(self.split('dev'))} dev, {len(self.split('test'))} test, "
            f"{len(self.split('hard'))} hard)"
        )

    # --- on disk ------------------------------------------------------------

    def to_json(self) -> dict:
        return {
            "version": self.version,
            "as_of": self.as_of.isoformat(),
            "notes": self.notes,
            # Sorted by id so the file is stable in git and a diff shows only
            # what actually changed.
            "questions": [q.to_json() for q in sorted(self.questions, key=lambda q: q.id)],
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2) + "\n")
        return path

    @classmethod
    def load(cls, path: str | Path) -> EvalSet:
        raw = json.loads(Path(path).read_text())
        built = cls(
            version=raw["version"],
            as_of=date.fromisoformat(raw["as_of"]),
            questions=[Question.from_json(row) for row in raw.get("questions", [])],
            notes=raw.get("notes", ""),
        )
        built.check()
        return built

    @classmethod
    def path_for(cls, version: str) -> Path:
        return EVAL_DIR / f"{version}.json"

    # --- integrity ----------------------------------------------------------

    def check(self) -> None:
        """Fail loudly on anything that would make a score meaningless."""
        ids = [q.id for q in self.questions]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            # A duplicated id makes results ambiguous and breaks the split,
            # since both copies would land in the same place.
            raise ValueError(f"{self.version}: duplicate question ids {duplicates}")

        wrong_as_of = [q.id for q in self.questions if q.as_of != self.as_of]
        if wrong_as_of:
            raise ValueError(
                f"{self.version}: these questions carry a different as-of date "
                f"from the set: {wrong_as_of[:5]}"
            )

        no_marker = [
            q.id
            for q in self.questions
            if q.kind == "injection" and not q.params.compliance_marker
        ]
        if no_marker:
            # An injection case with no marker cannot be graded, so it would
            # pass silently and make the robustness suite look clean.
            raise ValueError(f"{self.version}: injection cases with no marker: {no_marker}")


def deduplicate(questions: Iterable[Question]) -> list[Question]:
    """Keep the first question for each id."""
    seen: set[str] = set()
    kept = []
    for question in questions:
        if question.id in seen:
            continue
        seen.add(question.id)
        kept.append(question)
    return kept


def split_counts(questions: Sequence[Question]) -> dict[str, int]:
    return dict(Counter(split_for(q.id) for q in questions if q.kind != "document"))
