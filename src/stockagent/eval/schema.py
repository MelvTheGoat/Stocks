"""What a question is, and what a correct answer is.

Two decisions here shape the whole eval.

**A question stores its parameters, not its answer.** The text a reader sees is
generated from the same parameters the reference code uses, so the two cannot
drift. It also means the question set is publishable while the data is not: "what
did AAPL close at on 28 September 2026" carries no market data, whereas the
number does, and the provider's licence forbids redistributing that.

**Every question carries an as-of date.** Without one, "how has it done this
year" has a different right answer every morning, and a score from last week
cannot be compared with one from today. The agent is required to state the as-of
date in its answer for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from stockagent.data.models import Market

QuestionKind = Literal[
    # Straightforward lookups and arithmetic over the database.
    "price_on_date",
    "return_over_period",
    "compare_two",
    "best_in_group",
    "worst_in_group",
    "dividend_amount",
    "dividend_yield",
    "adjusted_return",
    "vs_benchmark",
    # Cases where the shape of the right answer is the point.
    "non_trading_day",
    "name_to_ticker",
    "unanswerable",
    "advice",
    "injection",
    # Questions drawn from documents, answered by hand.
    "document",
]

# Kinds where a correct answer refuses, redirects, or says there is no data.
# Grouped here because the graders treat them together and because forgetting
# one would mean scoring a refusal as a wrong number.
NON_NUMERIC_KINDS: frozenset[str] = frozenset(
    {"unanswerable", "advice", "injection", "name_to_ticker"}
)

Language = Literal["en", "pidgin"]


@dataclass(frozen=True)
class Params:
    """Everything the reference code needs to work an answer out.

    A flat record rather than a free-form dictionary, so a question missing the
    field its kind requires fails when it is built rather than halfway through
    a run on Kaggle.
    """

    tickers: tuple[str, ...] = ()
    day: date | None = None
    start: date | None = None
    end: date | None = None
    group: str = ""
    name: str = ""
    months: int | None = None
    # For injection cases: the instruction planted in a document, which the
    # agent must read as text and not obey.
    planted_instruction: str = ""

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.tickers:
            out["tickers"] = list(self.tickers)
        for name in ("day", "start", "end"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value.isoformat()
        for name in ("group", "name", "planted_instruction"):
            value = getattr(self, name)
            if value:
                out[name] = value
        if self.months is not None:
            out["months"] = self.months
        return out

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Params:
        return cls(
            tickers=tuple(raw.get("tickers", ())),
            day=_date(raw.get("day")),
            start=_date(raw.get("start")),
            end=_date(raw.get("end")),
            group=raw.get("group", ""),
            name=raw.get("name", ""),
            months=raw.get("months"),
            planted_instruction=raw.get("planted_instruction", ""),
        )


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@dataclass(frozen=True)
class Question:
    id: str
    kind: QuestionKind
    market: Market
    text: str
    as_of: date
    params: Params = field(default_factory=Params)
    language: Language = "en"
    # Free text for anything a human needs to know: why a case is here, or what
    # makes it hard.
    notes: str = ""

    def to_json(self) -> dict[str, Any]:
        out = {
            "id": self.id,
            "kind": self.kind,
            "market": self.market,
            "text": self.text,
            "as_of": self.as_of.isoformat(),
            "params": self.params.to_json(),
        }
        if self.language != "en":
            out["language"] = self.language
        if self.notes:
            out["notes"] = self.notes
        return out

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Question:
        return cls(
            id=raw["id"],
            kind=raw["kind"],
            market=raw["market"],
            text=raw["text"],
            as_of=date.fromisoformat(raw["as_of"]),
            params=Params.from_json(raw.get("params", {})),
            language=raw.get("language", "en"),
            notes=raw.get("notes", ""),
        )


TruthKind = Literal["number", "text", "refusal", "unanswerable"]


@dataclass(frozen=True)
class Truth:
    """The correct answer, worked out by reference code from the database.

    Never stored in the question file. Computed on demand, which keeps the
    provider's data out of the repository and means the answers cannot go stale
    against a corrected database.
    """

    kind: TruthKind
    number: float | None = None
    # "USD", "NGN", "percent", "ticker" -- so a grader can tell a 12% return
    # from twelve dollars.
    unit: str | None = None
    text: str | None = None
    # What the answer was derived from, for the source check.
    sources: tuple[str, ...] = ()
    # Plain sentence explaining the answer, shown in the labelling tool.
    explanation: str = ""

    @property
    def is_answerable(self) -> bool:
        return self.kind in ("number", "text")
