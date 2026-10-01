"""An LLM judge for free-text answers, and the check on whether to trust it.

Some answers cannot be graded by pattern. A question drawn from a document has a
correct answer in prose, and whether a candidate matches it is a judgement. So a
model makes that judgement.

The important part is not the judge. It is the check on the judge. A model asked
"is this answer correct?" tends to say yes, and a judge that says yes to
everything agrees with a human 90% of the time on a set where 90% of answers are
right -- while having learned nothing. Raw agreement hides that completely;
Cohen's kappa does not.

So `measure_agreement` exists, it is run against hand labels before any judged
number is reported, and `Agreement.trustworthy` is a hard gate: at least 30
labels and kappa of 0.6 or better. Below that the judge is not used. A
measurement nobody trusts is worse than no measurement, because it still gets
quoted.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from stockagent.agent.protocol import find_json_object
from stockagent.eval.schema import Question, Truth
from stockagent.eval.stats import Agreement, cohens_kappa
from stockagent.llm.base import ChatRequest, Message, ModelClient, ModelError, user

JUDGE_PROMPT = """\
You decide whether a candidate answer says the same thing as a reference answer.

You are strict about facts and relaxed about wording.

Mark it correct when:
- the figures match, allowing for rounding and for different ways of writing the
  same number
- the candidate says the same thing in different words
- the candidate adds extra correct detail

Mark it incorrect when:
- any figure differs beyond rounding
- the candidate states a figure the reference does not support
- the candidate answers a different question
- the reference says there is no data and the candidate gives a figure anyway
- the candidate gives investment advice

Being vague is not the same as being wrong, but a candidate too vague to check
against the reference is incorrect: an answer nobody can verify is not an answer.

Reply with one JSON object and nothing else:

{"correct": true or false, "reason": "one short sentence"}\
"""


@dataclass(frozen=True)
class JudgeVerdict:
    correct: bool
    reason: str
    # Set when the judge could not be read. Counted as incorrect, but reported
    # separately: a judge that often fails to answer is a broken judge, not a
    # strict one, and the two must not look the same.
    unreadable: bool = False
    raw: str = ""

    @property
    def label(self) -> str:
        """The form used for agreement measurement."""
        return "correct" if self.correct else "incorrect"


@dataclass
class LlmJudge:
    client: ModelClient
    model: str = "local"
    temperature: float = 0.0
    max_tokens: int = 200
    seed: int | None = 0
    prompt: str = JUDGE_PROMPT
    calls: list[ChatRequest] = field(default_factory=list, init=False)

    def judge(self, question: Question, truth: Truth, answer: str) -> JudgeVerdict:
        request = ChatRequest(
            model=self.model,
            messages=(
                Message(role="system", content=self.prompt),
                user(self._render(question, truth, answer)),
            ),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            seed=self.seed,
        )
        self.calls.append(request)

        try:
            response = self.client.chat(request)
        except ModelError as error:
            return JudgeVerdict(
                correct=False,
                reason=f"the judge could not be reached: {type(error).__name__}",
                unreadable=True,
            )

        return self._read(response.text)

    @staticmethod
    def _render(question: Question, truth: Truth, answer: str) -> str:
        reference = truth.explanation or truth.text or (
            "There is no data for this question; the correct answer says so."
        )
        return (
            f"Question: {question.text}\n"
            f"As of: {question.as_of.isoformat()}\n\n"
            f"Reference answer: {reference}\n\n"
            f"Candidate answer: {answer or '(the system gave no answer)'}"
        )

    @staticmethod
    def _read(text: str) -> JudgeVerdict:
        candidate = find_json_object(text)
        if candidate is None:
            return JudgeVerdict(
                False, "the judge did not reply with JSON", unreadable=True, raw=text[:300]
            )
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return JudgeVerdict(
                False, "the judge's JSON could not be parsed", unreadable=True, raw=text[:300]
            )
        if not isinstance(payload, dict) or "correct" not in payload:
            return JudgeVerdict(False, "the judge did not say correct or incorrect",
                                unreadable=True, raw=text[:300])

        verdict = payload["correct"]
        if isinstance(verdict, str):
            verdict = verdict.strip().lower() in ("true", "yes", "correct")
        return JudgeVerdict(
            correct=bool(verdict),
            reason=str(payload.get("reason", ""))[:300],
            raw=text[:300],
        )


@dataclass(frozen=True)
class HumanLabel:
    """One hand-checked verdict, as produced by the labelling tool."""

    question_id: str
    correct: bool
    note: str = ""

    @property
    def label(self) -> str:
        return "correct" if self.correct else "incorrect"


@dataclass
class JudgeCheck:
    """How well the judge agreed with a human, and whether to use it."""

    agreement: Agreement
    disagreements: list[tuple[str, str, str]] = field(default_factory=list)
    unreadable: int = 0

    @property
    def trustworthy(self) -> bool:
        return self.agreement.trustworthy and self.unreadable == 0

    def report(self) -> str:
        lines = [self.agreement.verdict()]
        if self.unreadable:
            lines.append(
                f"{self.unreadable} of the judge's replies could not be read. "
                "Fix that before trusting any judged figure: a judge that often "
                "fails to answer is broken, not strict."
            )
        if self.disagreements:
            lines.append(f"{len(self.disagreements)} disagreements, first few:")
            for question_id, human, judge in self.disagreements[:5]:
                lines.append(f"  {question_id}: human said {human}, judge said {judge}")
        lines.append(
            "The judge may be used for reported numbers."
            if self.trustworthy
            else "The judge must NOT be used for reported numbers yet."
        )
        return "\n".join(lines)


def measure_agreement(
    judge: LlmJudge,
    cases: Sequence[tuple[Question, Truth, str]],
    labels: Sequence[HumanLabel],
) -> JudgeCheck:
    """Run the judge over hand-labelled cases and compare.

    Only cases with a human label are compared. A judge scored against its own
    output would always look perfect.
    """
    by_id = {label.question_id: label for label in labels}

    human_labels: list[str] = []
    judge_labels: list[str] = []
    disagreements: list[tuple[str, str, str]] = []
    unreadable = 0

    for question, truth, answer in cases:
        label = by_id.get(question.id)
        if label is None:
            continue
        verdict = judge.judge(question, truth, answer)
        if verdict.unreadable:
            unreadable += 1
        human_labels.append(label.label)
        judge_labels.append(verdict.label)
        if label.label != verdict.label:
            disagreements.append((question.id, label.label, verdict.label))

    return JudgeCheck(
        agreement=cohens_kappa(human_labels, judge_labels),
        disagreements=disagreements,
        unreadable=unreadable,
    )
