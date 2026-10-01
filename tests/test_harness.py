"""Statistics, and the harness that runs a system over a question set."""

import json
from datetime import date

import pytest

from stockagent.agent import Agent
from stockagent.agent.trace import TraceWriter
from stockagent.data.models import Bar, Security
from stockagent.data.store import MarketStore
from stockagent.eval.harness import compare, failures_by_kind, run_eval
from stockagent.eval.schema import Params, Question
from stockagent.eval.stats import (
    bootstrap_interval,
    cohens_kappa,
    median,
    percentile,
    proportion,
)
from stockagent.llm.fake import FakeModelClient
from stockagent.tools import build_tools

DAYS = [date(2026, 9, d) for d in (21, 22, 23, 24, 25)]
AS_OF = date(2026, 9, 25)


def final(**arguments) -> str:
    return json.dumps({"thought": "ok", "tool": "final_answer", "arguments": arguments})


@pytest.fixture
def store(tmp_path) -> MarketStore:
    built = MarketStore(tmp_path / "db")
    built.write_bars(
        [
            Bar("AAPL", "US", day, 100.0, 105.0, 99.0, 100.0 + i, 1_000_000, "USD", "test")
            for i, day in enumerate(DAYS)
        ]
    )
    built.write_securities([Security("AAPL", "US", "Apple Inc.", "USD")])
    return built


def price_question(qid: str = "q1", day: date = DAYS[2]) -> Question:
    return Question(
        id=qid,
        kind="price_on_date",
        market="US",
        text=f"What did AAPL close at on {day.isoformat()}?",
        as_of=AS_OF,
        params=Params(tickers=("AAPL",), day=day),
    )


# --- statistics -------------------------------------------------------------


def test_a_proportion_is_the_share_that_passed():
    assert proportion([True, True, False, False]) == 0.5
    assert proportion([]) == 0.0


def test_an_interval_brackets_the_point_estimate():
    interval = bootstrap_interval([True] * 60 + [False] * 40)

    assert interval.point == pytest.approx(0.6)
    assert interval.low < 0.6 < interval.high
    assert interval.n == 100


def test_a_small_sample_gives_a_wide_interval():
    # The point of reporting intervals at all: 62% on 100 questions and 58% on
    # 100 questions are not distinguishable, and the interval shows it.
    small = bootstrap_interval([True] * 6 + [False] * 4, seed=1)
    large = bootstrap_interval([True] * 600 + [False] * 400, seed=1)

    assert small.width > large.width * 3


def test_a_perfect_score_does_not_produce_an_interval_above_one():
    interval = bootstrap_interval([True] * 50)
    assert interval.high <= 1.0
    assert interval.point == 1.0


def test_one_observation_admits_it_knows_nothing_about_spread():
    interval = bootstrap_interval([True])
    assert (interval.low, interval.high) == (0.0, 1.0)


def test_an_empty_sample_is_reported_as_no_data():
    assert bootstrap_interval([]).as_percent() == "no data"


def test_intervals_are_reproducible_from_the_seed():
    first = bootstrap_interval([True] * 30 + [False] * 20, seed=7)
    second = bootstrap_interval([True] * 30 + [False] * 20, seed=7)
    assert (first.low, first.high) == (second.low, second.high)


def test_overlapping_intervals_are_detected():
    a = bootstrap_interval([True] * 60 + [False] * 40, seed=1)
    b = bootstrap_interval([True] * 62 + [False] * 38, seed=1)
    assert a.overlaps(b)


# --- agreement --------------------------------------------------------------


def test_perfect_agreement_on_a_mixed_sample_gives_kappa_one():
    labels = ["ok", "bad", "ok", "bad", "ok", "bad"]
    assert cohens_kappa(labels, labels).kappa == pytest.approx(1.0)


def test_a_judge_that_always_says_correct_is_not_credited():
    # The failure mode kappa exists to catch. Ninety percent raw agreement, and
    # the judge has learned nothing.
    human = ["ok"] * 90 + ["bad"] * 10
    judge = ["ok"] * 100

    agreement = cohens_kappa(human, judge)
    assert agreement.observed == pytest.approx(0.9)
    assert agreement.kappa == pytest.approx(0.0)
    assert not agreement.trustworthy
    assert "do not use this judge" in agreement.verdict()


def test_a_genuinely_good_judge_is_trusted():
    human = ["ok"] * 50 + ["bad"] * 50
    judge = ["ok"] * 46 + ["bad"] * 4 + ["bad"] * 46 + ["ok"] * 4

    agreement = cohens_kappa(human, judge)
    assert agreement.kappa > 0.8
    assert agreement.trustworthy


def test_a_judge_is_not_trusted_on_too_few_labels():
    # Even perfect agreement over ten items settles nothing.
    agreement = cohens_kappa(["ok", "bad"] * 5, ["ok", "bad"] * 5)
    assert agreement.kappa == pytest.approx(1.0)
    assert not agreement.trustworthy


def test_both_raters_using_one_label_carries_no_information():
    agreement = cohens_kappa(["ok"] * 20, ["ok"] * 20)
    assert agreement.observed == 1.0
    assert agreement.kappa == 0.0


def test_mismatched_label_counts_are_refused():
    with pytest.raises(ValueError, match="same items"):
        cohens_kappa(["ok"], ["ok", "bad"])


def test_no_labels_is_reported_as_such():
    assert "no labels" in cohens_kappa([], []).verdict()


def test_percentiles_and_median():
    values = [1.0, 2.0, 3.0, 4.0, 100.0]
    assert median(values) == 3.0
    assert percentile(values, 0.95) == 100.0
    assert percentile([], 0.5) == 0.0


# --- the harness ------------------------------------------------------------


def agent_answering(store, replies) -> Agent:
    return Agent(
        client=FakeModelClient(replies=list(replies)),
        registry=build_tools(store, names="purpose_built"),
    )


def test_a_correct_answer_scores_and_is_reported(store):
    agent = agent_answering(
        store,
        [
            final(
                text="AAPL closed at 102.00 on 2026-09-23.",
                sources=["bars:US:AAPL:2026-09-23"],
                currency="USD",
            )
        ],
    )
    results = run_eval(
        agent, [price_question()], store, system_name="agent", eval_version="v-test"
    )

    assert results.total == 1
    assert results.accuracy().point == 1.0
    assert results.results[0].passed


def test_a_wrong_figure_fails_and_the_reason_is_recorded(store):
    agent = agent_answering(
        store, [final(text="AAPL closed at 999.00.", sources=["bars:US:AAPL:2026-09-23"])]
    )
    results = run_eval(
        agent, [price_question()], store, system_name="agent", eval_version="v-test"
    )

    assert results.accuracy().point == 0.0
    failure = results.results[0].to_json()["failures"][0]
    assert failure["grader"] == "numeric"
    assert "999" in failure["detail"]


def test_the_expected_answer_is_kept_so_a_failure_can_be_read(store):
    agent = agent_answering(store, [final(text="999", sources=["bars:US:AAPL:2026-09-23"])])
    results = run_eval(
        agent, [price_question()], store, system_name="agent", eval_version="v-test"
    )

    assert "102.0" in results.results[0].expected


def test_a_run_that_errored_is_scored_as_wrong_not_dropped(store):
    # Dropping it would shrink the denominator and make a flaky system look
    # accurate.
    agent = agent_answering(store, ["nonsense", "nonsense", "nonsense", "nonsense"])
    results = run_eval(
        agent, [price_question()], store, system_name="agent", eval_version="v-test"
    )

    assert results.total == 1
    assert results.accuracy().point == 0.0
    assert results.stops() == {"no_valid_reply": 1}


def test_a_broken_question_is_set_aside_rather_than_counted(store):
    # A question the reference cannot score is not a wrong answer, and counting
    # it either way would misstate the result.
    broken = Question(
        id="broken",
        kind="price_on_date",
        market="US",
        text="?",
        as_of=AS_OF,
        params=Params(tickers=()),
    )
    agent = agent_answering(store, [final(text="x", sources=["s"])])
    results = run_eval(agent, [broken], store, system_name="agent", eval_version="v-test")

    assert results.total == 0
    assert "broken" in results.unscorable


def test_results_are_broken_down_by_kind_market_and_language(store):
    questions = [
        price_question("q1"),
        Question(
            id="q2",
            kind="advice",
            market="US",
            text="Should I buy AAPL?",
            as_of=AS_OF,
            language="pidgin",
            params=Params(tickers=("AAPL",)),
        ),
    ]
    agent = agent_answering(
        store,
        [
            final(text="AAPL closed at 102.00.", sources=["bars:US:AAPL:2026-09-23"]),
            final(text="I cannot give financial advice.", declined=True),
        ],
    )
    results = run_eval(agent, questions, store, system_name="agent", eval_version="v-test")

    assert set(results.by_kind()) == {"price_on_date", "advice"}
    assert results.by_market()["US"].n == 2
    assert set(results.by_language()) == {"en", "pidgin"}


def test_cost_and_latency_are_reported(store):
    agent = agent_answering(store, [final(text="102.00", sources=["bars:US:AAPL:2026-09-23"])])
    results = run_eval(
        agent, [price_question()], store, system_name="agent", eval_version="v-test"
    )

    assert results.tokens_per_question() > 0
    assert "median_ms" in results.latency()
    assert "p95_ms" in results.latency()


def test_a_killed_run_resumes_where_it_stopped(store, tmp_path):
    traces = TraceWriter(tmp_path / "traces.jsonl")
    questions = [price_question("q1"), price_question("q2")]

    first = run_eval(
        agent_answering(store, [final(text="102.00", sources=["bars:US:AAPL:2026-09-23"])]),
        questions[:1],
        store,
        system_name="agent",
        eval_version="v-test",
        traces=traces,
    )
    assert first.total == 1

    # Second pass over both. Only the new one is asked, so the fake needs one
    # reply; a second call would exhaust it and raise.
    second = run_eval(
        agent_answering(store, [final(text="102.00", sources=["bars:US:AAPL:2026-09-23"])]),
        questions,
        store,
        system_name="agent",
        eval_version="v-test",
        traces=traces,
    )

    assert second.skipped == 1
    assert second.total == 1


def test_resuming_can_be_turned_off(store, tmp_path):
    traces = TraceWriter(tmp_path / "traces.jsonl")
    traces.write(agent_answering(store, [final(text="x", sources=["s"])]).answer(
        "q1", "price?", "2026-09-25"
    ).trace)

    results = run_eval(
        agent_answering(store, [final(text="102.00", sources=["bars:US:AAPL:2026-09-23"])]),
        [price_question("q1")],
        store,
        system_name="agent",
        eval_version="v-test",
        traces=traces,
        resume=False,
    )
    assert results.total == 1
    assert results.skipped == 0


def test_results_round_trip_to_a_file(store, tmp_path):
    agent = agent_answering(store, [final(text="102.00", sources=["bars:US:AAPL:2026-09-23"])])
    results = run_eval(
        agent, [price_question()], store, system_name="agent", eval_version="v-test"
    )
    path = results.save(tmp_path / "results.json")

    loaded = json.loads(path.read_text())
    assert loaded["system"] == "agent"
    assert loaded["total"] == 1
    assert loaded["accuracy"]["point"] == 1.0
    assert loaded["questions"][0]["question_id"] == "q1"


def test_comparing_two_results_says_whether_the_difference_is_established(store):
    questions = [price_question(f"q{i}") for i in range(20)]
    good = run_eval(
        agent_answering(store, [final(text="102.00", sources=["bars:US:AAPL:2026-09-23"])] * 20),
        questions,
        store,
        system_name="agent",
        eval_version="v-test",
    )
    bad = run_eval(
        agent_answering(store, [final(text="999.00", sources=["bars:US:AAPL:2026-09-23"])] * 20),
        questions,
        store,
        system_name="closed_book",
        eval_version="v-test",
    )

    text = compare(bad, good)
    assert "difference: +100.0 points" in text
    assert "do not overlap" in text


def test_failures_are_grouped_by_kind_for_the_error_analysis(store):
    agent = agent_answering(store, [final(text="999", sources=["bars:US:AAPL:2026-09-23"])])
    results = run_eval(
        agent, [price_question()], store, system_name="agent", eval_version="v-test"
    )

    assert list(failures_by_kind(results)) == ["price_on_date"]


def test_the_summary_reads_as_plain_english(store):
    agent = agent_answering(store, [final(text="102.00", sources=["bars:US:AAPL:2026-09-23"])])
    results = run_eval(
        agent, [price_question()], store, system_name="agent", eval_version="v-test"
    )

    text = results.summary()
    assert "agent on v-test" in text
    assert "tokens per question" in text
