"""The trace viewer, and the redaction that makes it publishable."""

import json
from datetime import date

import pytest

from stockagent.agent import Agent
from stockagent.agent.trace import TraceWriter
from stockagent.data.models import Bar, Security
from stockagent.data.store import MarketStore
from stockagent.eval.harness import run_eval
from stockagent.eval.schema import Params, Question
from stockagent.llm.fake import FakeModelClient
from stockagent.tools import build_tools
from stockagent.viewer import build, build_data, redact_figures, render

DAYS = [date(2026, 9, d) for d in (21, 22, 23, 24, 25)]


def final(**arguments) -> str:
    return json.dumps({"thought": "ok", "tool": "final_answer", "arguments": arguments})


@pytest.fixture
def run_files(tmp_path):
    """A real results file and its traces, produced by a real run."""
    store = MarketStore(tmp_path / "db")
    store.write_bars(
        [
            Bar("AAPL", "US", day, 100.0, 105.0, 99.0, 1066.70 + i, 1_234_567, "USD", "test")
            for i, day in enumerate(DAYS)
        ]
    )
    store.write_securities([Security("AAPL", "US", "Apple Inc.", "USD")])

    question = Question(
        id="q1",
        kind="price_on_date",
        market="US",
        text="What did AAPL close at on 2026-09-23?",
        as_of=date(2026, 9, 25),
        params=Params(tickers=("AAPL",), day=date(2026, 9, 23)),
    )
    agent = Agent(
        client=FakeModelClient(
            replies=[
                json.dumps(
                    {"tool": "get_prices", "arguments": {"ticker": "AAPL", "day": "2026-09-23"}}
                ),
                final(text="AAPL closed at 1999.00 USD.", sources=["bars:US:AAPL:2026-09-23"]),
            ]
        ),
        registry=build_tools(store, names="purpose_built"),
    )

    out = tmp_path / "out"
    traces = TraceWriter(out / "run-abc-traces.jsonl")
    results = run_eval(
        agent,
        [question],
        store,
        system_name="agent",
        eval_version="v-test",
        run_name="run-abc",
        traces=traces,
    )
    results.save(out / "run-abc-results.json")
    return [out / "run-abc-results.json"]


# --- redaction --------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("closed 1066.7000 dollars", "closed [figure] dollars"),
        ("volume 1234567", "volume [figure]"),
        ("open 99.00 high 105.00", "open [figure] high [figure]"),
    ],
)
def test_raw_figures_are_masked(text, expected):
    assert redact_figures(text) == expected


def test_dates_survive_redaction():
    # A trace with no dates in it is much less useful, and a date is not a price.
    masked = redact_figures("AAPL on 2026-09-23 closed 102.00")
    assert masked == "AAPL on 2026-09-23 closed [figure]"


def test_percentages_survive_redaction():
    # A return is derived data, and publishing it is permitted.
    assert redact_figures("it returned 18.5%") == "it returned 18.5%"


def test_small_whole_numbers_survive():
    # Step counts and factors are not prices.
    assert redact_figures("each share became 4 shares") == "each share became 4 shares"


def test_redaction_leaves_empty_text_alone():
    assert redact_figures("") == ""


# --- building the page ------------------------------------------------------


def test_the_page_is_built_from_a_real_run(run_files, tmp_path):
    path = build(run_files, tmp_path / "index.html")
    page = path.read_text()

    assert "<!doctype html>" in page.lower()
    assert "What did AAPL close at on 2026-09-23?" in page
    assert "get_prices" in page


def test_the_published_page_contains_no_raw_prices(run_files, tmp_path):
    # The whole point of redaction. A failure here would be a licence breach.
    page = build(run_files, tmp_path / "index.html", redact=True).read_text()

    # 1068.70 is the close the tool returned, 1234567 the volume.
    assert "1068.7" not in page
    assert "1234567" not in page
    assert "[figure]" in page


def test_the_local_page_keeps_the_figures_and_says_not_to_publish_it(run_files, tmp_path):
    page = build(run_files, tmp_path / "local.html", redact=False).read_text()

    assert "1068.7" in page
    assert "Do not publish this page" in page


def test_the_published_page_explains_why_figures_are_missing(run_files, tmp_path):
    page = build(run_files, tmp_path / "index.html", redact=True).read_text()
    assert "may not be republished" in page


def test_the_run_summary_reaches_the_page(run_files, tmp_path):
    data = build_data(run_files)
    (run,) = data.runs

    assert run["system"] == "agent"
    assert run["eval_version"] == "v-test"
    assert run["total"] == 1
    assert "point" in run["accuracy"]


def test_every_step_of_the_trace_is_present(run_files):
    (run,) = build_data(run_files).runs
    (question,) = run["questions"]

    kinds = [step["kind"] for step in question["steps"]]
    assert "model" in kinds
    assert "tool" in kinds
    assert question["tools"] == ["get_prices", "final_answer"]


def test_a_failure_carries_its_reason_to_the_page(run_files):
    (run,) = build_data(run_files).runs
    (question,) = run["questions"]

    # The scripted answer is deliberately wrong.
    assert question["passed"] is False
    assert question["failures"]
    assert question["failures"][0]["grader"] == "numeric"


def test_questions_can_be_capped_to_keep_the_page_small(run_files):
    data = build_data(run_files, max_questions=0)
    assert data.runs[0]["questions"] == []


def test_a_missing_traces_file_does_not_break_the_build(run_files, tmp_path):
    # Results can arrive without traces if a run was interrupted oddly.
    results = run_files[0]
    results.with_name(results.name.replace("-results.json", "-traces.jsonl")).unlink()

    (run,) = build_data([results]).runs
    assert run["questions"][0]["steps"] == []


def test_the_page_renders_with_no_runs_at_all():
    from stockagent.viewer import ViewerData

    page = render(ViewerData(title="Agent traces", runs=[]))
    assert "Agent traces" in page
    assert "const RUNS = []" in page


def test_the_embedded_data_is_valid_json(run_files, tmp_path):
    # A broken embed gives a blank page with a console error nobody sees.
    page = build(run_files, tmp_path / "index.html").read_text()
    start = page.index("const RUNS = ") + len("const RUNS = ")
    end = page.index(";\nlet current", start)

    parsed = json.loads(page[start:end])
    assert isinstance(parsed, list)
    assert parsed[0]["system"] == "agent"


def test_a_graders_failure_detail_is_redacted_too():
    # It quotes the expected figure ("expected 1068.7000 USD, closest was...") and
    # so leaks a raw price just as surely as a tool result does. This was a real
    # leak the publishable-page test caught.

    assert "[figure]" in redact_figures("expected 1068.7000 USD, closest was 1999.00 USD")
    assert "1068.7" not in redact_figures("expected 1068.7000 USD")
