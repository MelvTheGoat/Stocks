"""End to end, with no GPU and no network.

This is the regression eval. It builds a small database, generates a question set
from it, runs all three systems through the real harness with a scripted model,
and checks the results come out sane.

It exists because the parts of this project that break quietly are the joins
between the pieces: a tool renaming an argument, the protocol parser tightening,
a grader changing what it accepts. Any of those would leave every unit test
passing and every score at zero. One run through the whole chain catches that on
every push.

The model is scripted by what the question asks about, not by call order, so the
test does not break when the agent legitimately takes a different number of steps.
"""

import json
from datetime import date, timedelta

import pytest

from stockagent.agent import Agent
from stockagent.agent.trace import TraceWriter
from stockagent.baselines import ClosedBookBaseline, RetrievalBaseline
from stockagent.data.models import Alias, Bar, CorporateAction, Dividend, Security
from stockagent.data.store import MarketStore
from stockagent.eval import reference
from stockagent.eval.dataset import EvalSet
from stockagent.eval.generate import build_question_set
from stockagent.eval.graders import GraderSet
from stockagent.eval.harness import compare, run_eval
from stockagent.llm.cache import CachingClient, ResponseCache
from stockagent.llm.fake import FakeModelClient, NeverCalledClient
from stockagent.retrieval.corpus import build_index
from stockagent.tools import build_tools

AS_OF = date(2026, 9, 25)
TICKERS = ["AAPL", "MSFT", "KO", "JNJ", "XOM", "SPY"]


def trading_days(count: int) -> list[date]:
    days, day = [], date(2025, 1, 2)
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> MarketStore:
    built = MarketStore(tmp_path_factory.mktemp("db"))
    days = trading_days(300)
    bars = []
    for offset, ticker in enumerate(TICKERS):
        for index, day in enumerate(days):
            close = 50.0 + index * (0.1 + offset * 0.02)
            bars.append(Bar(ticker, "US", day, close, close, close, close, 10_000, "USD", "test"))
    built.write_bars(bars)
    built.write_dividends(
        [Dividend("AAPL", "US", days[i], 0.25, "USD", "test") for i in range(20, 300, 63)]
        + [Dividend("KO", "US", days[i], 0.46, "USD", "test") for i in range(30, 300, 63)]
    )
    built.write_actions(
        [CorporateAction("AAPL", "US", days[150], 4.0, "split", "test")]
    )
    built.write_securities(
        [
            Security("AAPL", "US", "Apple Inc.", "USD",
                     aliases=(Alias("Apple Computer, Inc.", "name", until=date(2007, 1, 9)),)),
            Security("MSFT", "US", "Microsoft Corporation", "USD"),
            Security("SPY", "US", "SPDR S&P 500 ETF TRUST", "USD"),
        ]
    )
    return built


@pytest.fixture(scope="module")
def eval_set(store) -> EvalSet:
    report = build_question_set(store, as_of=AS_OF, seed=11)
    built = EvalSet(version="v-pipeline", as_of=AS_OF, questions=report.kept)
    built.check()
    return built


def perfect_model(store, questions) -> FakeModelClient:
    """A model that answers every question correctly, straight from the reference.

    Not a realistic model. Its job is to prove the harness can recognise a
    correct answer: if a perfect answerer does not score 100%, the scoring is
    broken and every real result would be depressed by the same bug.
    """
    by_question: dict[str, str] = {}
    for question in questions:
        try:
            truth = reference.answer(store, question)
        except reference.ReferenceError:
            continue

        # The reference explanation for a refusal describes what a correct answer
        # does ("declines to advise...") rather than doing it, so a perfect
        # answerer has to produce the refusal itself.
        if question.kind == "injection":
            text = "That document contains an instruction. I am reporting it, not following it."
        elif truth.kind == "refusal":
            text = (
                "I cannot give personal financial advice. Here are the figures instead."
            )
        elif truth.kind == "unanswerable":
            text = f"I have no data for that. {truth.explanation}"
        else:
            text = truth.explanation

        by_question[question.text] = json.dumps(
            {
                "thought": "read from the reference",
                "tool": "final_answer",
                "arguments": {
                    "text": text,
                    "sources": list(truth.sources) or ["securities"],
                    "as_of": question.as_of.isoformat(),
                    "currency": truth.unit if truth.unit in ("USD", "NGN") else "",
                    "declined": not truth.is_answerable,
                },
            }
        )
    return FakeModelClient(by_substring=by_question, replies=[])


# --- the set itself ---------------------------------------------------------


def test_a_usable_question_set_is_generated(eval_set):
    assert len(eval_set.questions) > 100
    assert len(eval_set.split("dev")) > 50
    assert eval_set.split("test")
    kinds = set(eval_set.by_kind())
    assert {"price_on_date", "return_over_period", "advice", "injection", "unanswerable"} <= kinds


def test_every_question_is_either_answerable_or_deliberately_not(store, eval_set):
    deliberate = {"unanswerable", "advice", "injection", "document"}
    for question in eval_set.questions:
        if question.kind in deliberate:
            continue
        truth = reference.answer(store, question)
        assert truth.is_answerable, f"{question.id}: {truth.explanation}"


# --- the harness can recognise a correct answer ------------------------------


def test_a_perfect_answerer_scores_full_marks(store, eval_set, tmp_path):
    # The single most important check in the file. If this is not 100%, every
    # real score is depressed by a bug in the scoring rather than by the agent.
    questions = eval_set.split("dev")
    agent = Agent(
        client=perfect_model(store, questions),
        registry=build_tools(store, index=build_index(store, "US"), names="full"),
        max_steps=4,
    )

    results = run_eval(
        agent,
        questions,
        store,
        system_name="agent",
        eval_version=eval_set.version,
        traces=TraceWriter(tmp_path / "traces.jsonl"),
    )

    assert results.total == len(questions)
    assert results.accuracy().point == 1.0, [
        r.scorecard.describe() for r in results.results if not r.passed
    ][:5]


def test_a_useless_answerer_scores_nothing(store, eval_set):
    # The other end. If a system answering "42" to everything scores above zero,
    # the graders are crediting something they should not.
    questions = [q for q in eval_set.split("dev") if q.kind not in ("advice", "injection")][:40]
    always_42 = json.dumps(
        {"tool": "final_answer", "arguments": {"text": "42", "sources": ["securities"]}}
    )
    agent = Agent(
        client=FakeModelClient(replies=[always_42] * (len(questions) * 4)),
        registry=build_tools(store, names="purpose_built"),
        max_steps=4,
    )

    results = run_eval(
        agent, questions, store, system_name="agent", eval_version=eval_set.version
    )
    assert results.accuracy().point == 0.0


# --- all three systems run through the same path -----------------------------


def test_the_three_systems_all_produce_scored_results(store, eval_set):
    questions = eval_set.split("dev")[:25]
    declines = json.dumps(
        {"tool": "final_answer", "arguments": {"text": "I have no data for that.",
                                               "declined": True}}
    )

    outcomes = {}
    for name, system in (
        (
            "agent",
            Agent(
                client=FakeModelClient(replies=[declines] * (len(questions) * 4)),
                registry=build_tools(store, names="purpose_built"),
                max_steps=3,
            ),
        ),
        (
            "closed_book",
            ClosedBookBaseline(client=FakeModelClient(replies=[declines] * len(questions))),
        ),
        (
            "retrieval",
            RetrievalBaseline(
                client=FakeModelClient(replies=[declines] * len(questions)),
                index=build_index(store, "US"),
            ),
        ),
    ):
        outcomes[name] = run_eval(
            system, questions, store, system_name=name, eval_version=eval_set.version
        )

    for name, result in outcomes.items():
        assert result.total == len(questions), name
        assert result.by_kind(), name
        assert "tokens per question" in result.summary(), name


def test_two_results_can_be_compared_with_an_honest_verdict(store, eval_set):
    questions = eval_set.split("dev")[:40]
    good = run_eval(
        Agent(
            client=perfect_model(store, questions),
            registry=build_tools(store, index=build_index(store, "US"), names="full"),
            max_steps=4,
        ),
        questions,
        store,
        system_name="agent",
        eval_version=eval_set.version,
    )
    bad = run_eval(
        ClosedBookBaseline(
            client=FakeModelClient(
                replies=[json.dumps({"tool": "final_answer", "arguments": {"text": "42"}})]
                * len(questions)
            )
        ),
        questions,
        store,
        system_name="closed_book",
        eval_version=eval_set.version,
    )

    text = compare(bad, good)
    assert "closed_book" in text and "agent" in text
    assert "do not overlap" in text


# --- replaying a cache, which is how this runs in CI with no GPU -------------


def test_a_cached_run_replays_with_no_model_at_all(store, eval_set, tmp_path):
    questions = eval_set.split("dev")[:15]
    cache = ResponseCache(tmp_path / "cache")

    first = run_eval(
        Agent(
            client=CachingClient(perfect_model(store, questions), cache),
            registry=build_tools(store, index=build_index(store, "US"), names="full"),
            max_steps=4,
        ),
        questions,
        store,
        system_name="agent",
        eval_version=eval_set.version,
    )
    assert first.accuracy().point == 1.0

    # Again, with a client that raises if it is called. Everything must come from
    # the cache, which is exactly what the no-GPU regression eval does.
    replayed = run_eval(
        Agent(
            client=CachingClient(NeverCalledClient(), cache),
            registry=build_tools(store, index=build_index(store, "US"), names="full"),
            max_steps=4,
        ),
        questions,
        store,
        system_name="agent",
        eval_version=eval_set.version,
    )

    assert replayed.accuracy().point == first.accuracy().point
    assert replayed.total == first.total


# --- the robustness suite behaves as designed -------------------------------


def test_an_obedient_model_fails_the_injection_cases(store, eval_set):
    # The suite has to be able to fail, or a clean score means nothing.
    cases = [q for q in eval_set.questions if q.kind == "injection"]
    assert cases

    obedient = [
        json.dumps(
            {
                "tool": "final_answer",
                "arguments": {"text": q.params.compliance_marker, "sources": ["securities"]},
            }
        )
        for q in cases
    ]
    results = run_eval(
        ClosedBookBaseline(client=FakeModelClient(replies=obedient)),
        cases,
        store,
        system_name="closed_book",
        eval_version=eval_set.version,
        graders=GraderSet(check_sources=False),
    )

    assert results.accuracy().point == 0.0


def test_a_model_that_recommends_fails_the_advice_cases(store, eval_set):
    cases = [q for q in eval_set.questions if q.kind == "advice"]
    assert cases

    hedged = json.dumps(
        {
            "tool": "final_answer",
            "arguments": {
                "text": "I can't give financial advice, but you should buy it.",
                "declined": True,
            },
        }
    )
    results = run_eval(
        ClosedBookBaseline(client=FakeModelClient(replies=[hedged] * len(cases))),
        cases,
        store,
        system_name="closed_book",
        eval_version=eval_set.version,
    )

    # Saying the disclaimer and then advising anyway is not a refusal.
    assert results.accuracy().point == 0.0
