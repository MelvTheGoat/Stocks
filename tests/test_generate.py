"""Generating the question set, and the hand-written cases."""

from datetime import date, timedelta

import pytest

from stockagent.data.models import Alias, Bar, Dividend, Security
from stockagent.data.store import MarketStore
from stockagent.eval import reference
from stockagent.eval.cases import all_cases, injection_cases, pidgin_cases
from stockagent.eval.dataset import EvalSet
from stockagent.eval.generate import build_question_set, generate
from stockagent.eval.graders import GraderSet

AS_OF = date(2026, 9, 25)
TICKERS = ["AAPL", "MSFT", "NVDA", "KO", "JNJ", "SPY"]


def trading_days(count: int) -> list[date]:
    days, day = [], date(2024, 1, 2)
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


@pytest.fixture
def store(tmp_path) -> MarketStore:
    built = MarketStore(tmp_path / "db")
    days = trading_days(400)
    bars = []
    for offset, ticker in enumerate(TICKERS):
        for index, day in enumerate(days):
            close = 100.0 + index * (0.05 + offset * 0.01)
            bars.append(Bar(ticker, "US", day, close, close, close, close, 1000, "USD", "test"))
    built.write_bars(bars)
    built.write_dividends(
        [
            Dividend("AAPL", "US", days[i], 0.25, "USD", "test")
            for i in range(20, 400, 63)
        ]
        + [Dividend("KO", "US", days[i], 0.46, "USD", "test") for i in range(30, 400, 63)]
    )
    built.write_securities(
        [
            Security("AAPL", "US", "Apple Inc.", "USD"),
            Security(
                "MSFT",
                "US",
                "Microsoft Corporation",
                "USD",
                aliases=(Alias("Micro-Soft", "name", until=date(1987, 1, 1)),),
            ),
        ]
    )
    return built


# --- generation -------------------------------------------------------------


def test_a_set_is_generated_across_many_kinds(store):
    report = generate(store, as_of=AS_OF)

    kinds = {question.kind for question in report.kept}
    assert len(report.kept) > 100
    assert {"price_on_date", "return_over_period", "compare_two", "vs_benchmark"} <= kinds


def test_generation_is_reproducible_from_the_seed(store):
    first = generate(store, as_of=AS_OF, seed=7)
    second = generate(store, as_of=AS_OF, seed=7)

    assert [q.text for q in first.kept] == [q.text for q in second.kept]


def test_a_different_seed_gives_different_questions(store):
    first = generate(store, as_of=AS_OF, seed=1)
    second = generate(store, as_of=AS_OF, seed=2)

    assert [q.text for q in first.kept] != [q.text for q in second.kept]


def test_every_generated_question_can_be_answered_by_the_reference(store):
    # The property that keeps the score meaningful. A question that cannot be
    # scored subtracts a constant from every result that nobody can account for.
    report = generate(store, as_of=AS_OF)

    for question in report.kept:
        truth = reference.answer(store, question)
        assert truth.is_answerable, f"{question.id}: {truth.explanation}"


def test_questions_the_reference_cannot_answer_are_dropped_with_a_reason(store):
    # KO and JNJ pay no dividends in this fixture for some windows, so some
    # dividend questions will be dropped. Whatever is dropped must say why.
    report = generate(store, as_of=AS_OF)
    assert all(reason for reason in report.dropped.values())


def test_every_question_carries_the_as_of_date(store):
    for question in generate(store, as_of=AS_OF).kept:
        assert question.as_of == AS_OF


def test_ids_are_unique(store):
    ids = [q.id for q in generate(store, as_of=AS_OF).kept]
    assert len(ids) == len(set(ids))


def test_the_benchmark_is_not_asked_about_as_if_it_were_a_company(store):
    # "Did SPY beat SPY" is not a question.
    for question in generate(store, as_of=AS_OF).kept:
        if question.kind == "vs_benchmark":
            assert question.params.tickers[0] != "SPY"


def test_non_trading_day_questions_really_land_on_closed_days(store):
    from stockagent.data.calendar import TradingCalendar

    calendar = TradingCalendar.from_store(store, "US")
    asked = [q for q in generate(store, as_of=AS_OF).kept if q.kind == "non_trading_day"]

    assert asked
    for question in asked:
        assert not calendar.is_trading_day(question.params.day)


def test_an_empty_database_generates_nothing_rather_than_failing(tmp_path):
    report = generate(MarketStore(tmp_path / "empty"), as_of=AS_OF)

    assert report.kept == []
    assert report.dropped


def test_former_names_become_questions(store):
    texts = [q.text for q in generate(store, as_of=AS_OF).kept if q.kind == "name_to_ticker"]
    assert any("Micro-Soft" in text for text in texts)


# --- the hand-written cases -------------------------------------------------


def test_the_full_set_includes_the_robustness_cases(store):
    report = build_question_set(store, as_of=AS_OF)
    kinds = {q.kind for q in report.kept}

    assert {"advice", "injection", "unanswerable"} <= kinds
    assert any(q.language == "pidgin" for q in report.kept)


def test_every_injection_case_has_a_compliance_marker():
    # Without one the case cannot be graded and would pass silently.
    for question in injection_cases(AS_OF):
        assert question.params.compliance_marker
        assert question.params.planted_instruction


def test_pidgin_cases_are_marked_as_pidgin():
    for question in pidgin_cases(AS_OF):
        assert question.language == "pidgin"


def test_pidgin_cases_cover_more_than_one_kind():
    # If they were all price lookups, a gap would say nothing about whether the
    # phrasing affects harder reasoning.
    assert len({q.kind for q in pidgin_cases(AS_OF)}) >= 4


def test_the_hand_written_cases_have_unique_ids():
    ids = [q.id for q in all_cases(AS_OF)]
    assert len(ids) == len(set(ids))


def test_the_generated_set_passes_the_eval_files_own_checks(store):
    report = build_question_set(store, as_of=AS_OF)
    EvalSet(version="v-test", as_of=AS_OF, questions=report.kept).check()


# --- the graders agree with the reference on generated questions ------------


def test_a_perfect_answer_scores_full_marks_on_every_generated_question(store):
    """The reference explanation, fed back in as an answer, must grade as correct.

    This is the closest thing to a test of the eval itself. If a grader cannot
    recognise the reference's own wording as right, it will not recognise a
    correct agent answer either, and every score would be depressed by a bug in
    the scoring rather than by the agent.
    """
    graders = GraderSet()
    report = generate(store, as_of=AS_OF, seed=3)

    checked = 0
    for question in report.kept:
        truth = reference.answer(store, question)
        card = graders.grade(question, truth, truth.explanation)
        assert card.passed, f"{question.id} ({question.kind}): {card.describe()}"
        checked += 1

    assert checked > 100
