"""The LLM judge, and the check that decides whether it can be trusted."""

import json
from datetime import date

import pytest

from stockagent.eval.judge import HumanLabel, LlmJudge, measure_agreement
from stockagent.eval.schema import Params, Question, Truth
from stockagent.llm.base import TransientModelError
from stockagent.llm.fake import FakeModelClient

AS_OF = date(2026, 9, 25)


def question(qid: str = "d1") -> Question:
    return Question(
        id=qid,
        kind="document",
        market="US",
        text="What does the filing say about revenue?",
        as_of=AS_OF,
        params=Params(),
    )


def truth(explanation: str = "Revenue was 94.9 billion dollars.") -> Truth:
    return Truth(kind="text", text=explanation, explanation=explanation)


def verdict(correct: bool, reason: str = "matches") -> str:
    return json.dumps({"correct": correct, "reason": reason})


# --- reading the judge ------------------------------------------------------


def test_a_clear_verdict_is_read():
    judge = LlmJudge(client=FakeModelClient(replies=[verdict(True, "figures match")]))
    result = judge.judge(question(), truth(), "Revenue was 94.9bn.")

    assert result.correct
    assert result.reason == "figures match"
    assert not result.unreadable


def test_an_incorrect_verdict_is_read():
    judge = LlmJudge(client=FakeModelClient(replies=[verdict(False, "figure differs")]))
    assert not judge.judge(question(), truth(), "Revenue was 12bn.").correct


def test_a_verdict_written_as_a_string_is_accepted():
    judge = LlmJudge(client=FakeModelClient(replies=['{"correct": "yes", "reason": "ok"}']))
    assert judge.judge(question(), truth(), "x").correct


def test_a_fenced_reply_is_still_read():
    judge = LlmJudge(
        client=FakeModelClient(replies=['```json\n{"correct": true, "reason": "ok"}\n```'])
    )
    assert judge.judge(question(), truth(), "x").correct


@pytest.mark.parametrize(
    "reply", ["I think it is correct.", "", "{broken json", '{"reason": "no verdict"}']
)
def test_an_unreadable_reply_counts_as_incorrect_but_is_flagged(reply):
    # A judge that often fails to answer is broken, not strict, and the two must
    # not look the same in a report.
    judge = LlmJudge(client=FakeModelClient(replies=[reply]))
    result = judge.judge(question(), truth(), "x")

    assert not result.correct
    assert result.unreadable


def test_a_dead_model_is_reported_not_raised():
    class Failing:
        def chat(self, request):
            raise TransientModelError("gone")

    result = LlmJudge(client=Failing()).judge(question(), truth(), "x")
    assert result.unreadable
    assert "could not be reached" in result.reason


def test_the_question_reference_and_candidate_all_reach_the_judge():
    judge = LlmJudge(client=FakeModelClient(replies=[verdict(True)]))
    judge.judge(question(), truth("Revenue was 94.9 billion."), "Revenue was 94.9bn.")

    sent = judge.calls[0].messages[-1].content
    assert "What does the filing say" in sent
    assert "Revenue was 94.9 billion." in sent
    assert "Revenue was 94.9bn." in sent
    assert "2026-09-25" in sent


def test_an_empty_answer_is_described_rather_than_sent_blank():
    judge = LlmJudge(client=FakeModelClient(replies=[verdict(False)]))
    judge.judge(question(), truth(), "")

    assert "gave no answer" in judge.calls[0].messages[-1].content


def test_a_truth_with_no_explanation_still_renders():
    judge = LlmJudge(client=FakeModelClient(replies=[verdict(False)]))
    judge.judge(question(), Truth(kind="unanswerable"), "It was 10 dollars.")

    assert "no data for this question" in judge.calls[0].messages[-1].content


# --- the check on the judge -------------------------------------------------


def cases(count: int):
    return [(question(f"d{i}"), truth(), f"answer {i}") for i in range(count)]


def test_a_judge_agreeing_with_every_label_is_trusted():
    labels = [HumanLabel(f"d{i}", correct=(i % 2 == 0)) for i in range(40)]
    replies = [verdict(i % 2 == 0) for i in range(40)]
    judge = LlmJudge(client=FakeModelClient(replies=replies))

    check = measure_agreement(judge, cases(40), labels)

    assert check.agreement.kappa == pytest.approx(1.0)
    assert check.trustworthy
    assert "may be used" in check.report()


def test_a_judge_that_says_correct_to_everything_is_not_trusted():
    # The failure this whole check exists to catch. 90% raw agreement, worthless.
    labels = [HumanLabel(f"d{i}", correct=(i < 36)) for i in range(40)]
    judge = LlmJudge(client=FakeModelClient(replies=[verdict(True)] * 40))

    check = measure_agreement(judge, cases(40), labels)

    assert check.agreement.observed == pytest.approx(0.9)
    assert check.agreement.kappa == pytest.approx(0.0)
    assert not check.trustworthy
    assert "must NOT be used" in check.report()


def test_too_few_labels_is_not_enough_however_good_the_agreement():
    labels = [HumanLabel(f"d{i}", correct=(i % 2 == 0)) for i in range(10)]
    judge = LlmJudge(client=FakeModelClient(replies=[verdict(i % 2 == 0) for i in range(10)]))

    check = measure_agreement(judge, cases(10), labels)

    assert check.agreement.kappa == pytest.approx(1.0)
    assert not check.trustworthy


def test_unreadable_replies_block_trust_even_with_good_agreement():
    labels = [HumanLabel(f"d{i}", correct=(i % 2 == 0)) for i in range(40)]
    replies = [verdict(i % 2 == 0) for i in range(39)] + ["I am not sure."]
    judge = LlmJudge(client=FakeModelClient(replies=replies))

    check = measure_agreement(judge, cases(40), labels)

    assert check.unreadable == 1
    assert not check.trustworthy
    assert "could not be read" in check.report()


def test_disagreements_are_listed_so_they_can_be_read():
    labels = [HumanLabel("d0", correct=True), HumanLabel("d1", correct=False)]
    judge = LlmJudge(client=FakeModelClient(replies=[verdict(True), verdict(True)]))

    check = measure_agreement(judge, cases(2), labels)

    assert check.disagreements == [("d1", "incorrect", "correct")]
    assert "human said incorrect, judge said correct" in check.report()


def test_only_labelled_cases_are_compared():
    # A judge scored against its own output would always look perfect.
    labels = [HumanLabel("d0", correct=True)]
    judge = LlmJudge(client=FakeModelClient(replies=[verdict(True)]))

    check = measure_agreement(judge, cases(5), labels)

    assert check.agreement.n == 1
    assert judge.calls and len(judge.calls) == 1


def test_no_labels_at_all_is_reported_rather_than_passing():
    judge = LlmJudge(client=FakeModelClient(replies=[]))
    check = measure_agreement(judge, cases(3), [])

    assert check.agreement.n == 0
    assert not check.trustworthy
    assert "no labels" in check.report()
