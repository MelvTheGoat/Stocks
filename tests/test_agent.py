"""The agent loop, driven by a scripted model. No network, no real model."""

import json
from datetime import date

import pytest

from stockagent.agent import Agent, Trace, parse_tool_call
from stockagent.agent.protocol import ParseFailure, ToolCall, find_json_object
from stockagent.agent.trace import TraceWriter
from stockagent.data.models import Bar, CorporateAction, Security
from stockagent.data.store import MarketStore
from stockagent.llm.base import TransientModelError
from stockagent.llm.fake import FakeModelClient
from stockagent.tools import build_tools

DAYS = [date(2026, 9, d) for d in (21, 22, 23, 24, 25)]


def call(tool: str, **arguments) -> str:
    return json.dumps({"thought": "because", "tool": tool, "arguments": arguments})


@pytest.fixture
def store(tmp_path) -> MarketStore:
    built = MarketStore(tmp_path / "db")
    built.write_bars(
        [
            Bar("AAPL", "US", day, 100.0, 105.0, 99.0, 100.0 + i, 1_000_000, "USD", "test")
            for i, day in enumerate(DAYS)
        ]
    )
    built.write_actions([CorporateAction("AAPL", "US", date(2020, 8, 31), 4.0, "split", "test")])
    built.write_securities([Security("AAPL", "US", "Apple Inc.", "USD")])
    return built


def agent_with(store, replies, **overrides) -> Agent:
    client = FakeModelClient(replies=list(replies))
    settings = {
        "client": client,
        "registry": build_tools(store, names="purpose_built"),
        "max_steps": 6,
    }
    settings.update(overrides)
    built = Agent(**settings)
    built.client_ref = client  # type: ignore[attr-defined]
    return built


# --- the protocol -----------------------------------------------------------


def test_a_plain_json_object_is_read():
    parsed = parse_tool_call('{"tool": "get_prices", "arguments": {"ticker": "AAPL"}}')
    assert isinstance(parsed, ToolCall)
    assert parsed.tool == "get_prices"
    assert parsed.arguments == {"ticker": "AAPL"}


@pytest.mark.parametrize(
    "reply",
    [
        '```json\n{"tool": "calculate", "arguments": {"expression": "1+1"}}\n```',
        'Sure, here you go:\n{"tool": "calculate", "arguments": {"expression": "1+1"}}',
        '{"tool": "calculate", "arguments": {"expression": "1+1"}}\n\nHope that helps!',
        '```\n{"tool": "calculate", "arguments": {"expression": "1+1"}}\n```',
    ],
)
def test_models_being_chatty_does_not_break_parsing(reply):
    # A strict parser would score a chatty model badly for being chatty rather
    # than for being wrong, and the comparison would measure the wrong thing.
    parsed = parse_tool_call(reply)
    assert isinstance(parsed, ToolCall)
    assert parsed.tool == "calculate"


def test_braces_inside_strings_do_not_confuse_the_scanner():
    reply = '{"tool": "calculate", "arguments": {"expression": "1+1"}, "thought": "a } brace"}'
    parsed = parse_tool_call(reply)
    assert isinstance(parsed, ToolCall)
    assert parsed.thought == "a } brace"


def test_double_encoded_arguments_are_unwrapped():
    reply = '{"tool": "calculate", "arguments": "{\\"expression\\": \\"1+1\\"}"}'
    parsed = parse_tool_call(reply)
    assert isinstance(parsed, ToolCall)
    assert parsed.arguments == {"expression": "1+1"}


@pytest.mark.parametrize(
    "reply",
    ["I think it is about 100 dollars.", "", "{not json at all}", '{"arguments": {}}', "[1, 2]"],
)
def test_unreadable_replies_are_failures_with_guidance(reply):
    parsed = parse_tool_call(reply)
    assert isinstance(parsed, ParseFailure)
    assert "JSON object" in parsed.guidance


def test_finding_an_object_returns_none_when_there_is_none():
    assert find_json_object("no braces here") is None


# --- the happy path ---------------------------------------------------------


def test_the_agent_looks_up_a_price_and_answers(store):
    agent = agent_with(
        store,
        [
            call("get_prices", ticker="AAPL", day="2026-09-23"),
            call(
                "final_answer",
                text="AAPL closed at 102.00 on 2026-09-23.",
                sources=["bars:US:AAPL:2026-09-23"],
                currency="USD",
                as_of="2026-09-25",
            ),
        ],
    )
    outcome = agent.answer("q1", "What did AAPL close at on 2026-09-23?", "2026-09-25")

    assert outcome.answered
    assert "102.00" in outcome.text()
    assert "As of 2026-09-25" in outcome.text()
    assert outcome.trace.tool_calls == 2


def test_the_trace_records_tokens_latency_and_the_tools_used(store):
    agent = agent_with(
        store,
        [
            call("get_corporate_actions", ticker="AAPL"),
            call("final_answer", text="It split four for one.", sources=["actions:US:AAPL"]),
        ],
    )
    outcome = agent.answer("q1", "Did AAPL split?", "2026-09-25")

    assert outcome.trace.model_calls == 2
    assert outcome.trace.total_tokens > 0
    assert outcome.trace.latency_ms >= 0
    assert "get_corporate_actions" in outcome.trace.tools_used()


# --- recovery ---------------------------------------------------------------


def test_a_single_unparseable_reply_is_coached_and_the_run_continues(store):
    agent = agent_with(
        store,
        [
            "I'll look that up for you.",
            call("get_prices", ticker="AAPL", day="2026-09-23"),
            call("final_answer", text="102.00", sources=["bars:US:AAPL:2026-09-23"]),
        ],
    )
    outcome = agent.answer("q1", "price?", "2026-09-25")

    assert outcome.answered
    # The failure is on the record, because a model needing extra turns is more
    # expensive and that belongs in the comparison.
    assert any(step.detail.get("problem") == "parse_failure" for step in outcome.trace.steps)


def test_persistent_nonsense_ends_the_run_without_an_answer(store):
    agent = agent_with(store, ["nope", "still nope", "nope again", "and again"])
    outcome = agent.answer("q1", "price?", "2026-09-25")

    assert outcome.stop == "no_valid_reply"
    assert outcome.text() == ""


def test_a_tool_failure_is_handed_back_so_the_agent_can_decline(store):
    agent = agent_with(
        store,
        [
            call("get_prices", ticker="AAPL", day="2027-06-01"),
            call(
                "final_answer",
                text="I have no data for that date.",
                declined=True,
            ),
        ],
    )
    outcome = agent.answer("q1", "price in 2027?", "2026-09-25")

    assert outcome.answered
    assert outcome.answer.declined
    assert outcome.trace.failed_tool_calls() == 1


def test_an_answer_with_no_sources_is_sent_back_once(store):
    agent = agent_with(
        store,
        [
            call("final_answer", text="About 102."),
            call("final_answer", text="102.00", sources=["bars:US:AAPL:2026-09-23"]),
        ],
    )
    outcome = agent.answer("q1", "price?", "2026-09-25")

    assert outcome.answered
    assert outcome.answer.sources == ("bars:US:AAPL:2026-09-23",)


def test_calling_a_tool_that_does_not_exist_is_recoverable(store):
    agent = agent_with(
        store,
        [
            call("get_vibes", ticker="AAPL"),
            call("final_answer", text="102.00", sources=["bars:US:AAPL:2026-09-23"]),
        ],
    )
    assert agent.answer("q1", "price?", "2026-09-25").answered


# --- the limits -------------------------------------------------------------


def test_running_out_of_steps_is_scored_as_wrong_not_dropped(store):
    # Dropping it would quietly improve the accuracy figure by removing the
    # questions the agent could not finish.
    agent = agent_with(
        store, [call("get_prices", ticker="AAPL", day="2026-09-23")] * 10, max_steps=3
    )
    outcome = agent.answer("q1", "price?", "2026-09-25")

    assert outcome.stop == "out_of_steps"
    assert outcome.text() == ""
    assert "within 3 steps" in outcome.detail


def test_the_step_limit_is_respected_exactly(store):
    agent = agent_with(
        store, [call("get_prices", ticker="AAPL", day="2026-09-23")] * 10, max_steps=4
    )
    outcome = agent.answer("q1", "price?", "2026-09-25")

    assert outcome.trace.model_calls == 4


def test_a_model_error_ends_the_question_without_losing_the_trace(store):
    class Failing:
        def chat(self, request):
            raise TransientModelError("the server went away")

    agent = Agent(client=Failing(), registry=build_tools(store, names="purpose_built"))
    outcome = agent.answer("q1", "price?", "2026-09-25")

    assert outcome.stop == "model_error"
    assert "TransientModelError" in outcome.detail
    assert outcome.trace.steps


# --- the self-check pass (Experiment D) -------------------------------------


def test_the_self_check_sends_the_agent_back_once(store):
    agent = agent_with(
        store,
        [
            call("final_answer", text="102.00", sources=["bars:US:AAPL:2026-09-23"]),
            call("get_prices", ticker="AAPL", day="2026-09-23"),
            call("final_answer", text="102.00 confirmed", sources=["bars:US:AAPL:2026-09-23"]),
        ],
        self_check=True,
    )
    outcome = agent.answer("q1", "price?", "2026-09-25")

    assert outcome.answered
    assert "confirmed" in outcome.answer.text
    assert any(step.detail.get("note") == "self_check_requested" for step in outcome.trace.steps)


def test_the_self_check_asks_only_once(store):
    agent = agent_with(
        store,
        [
            call("final_answer", text="first", sources=["s"]),
            call("final_answer", text="second", sources=["s"]),
        ],
        self_check=True,
    )
    outcome = agent.answer("q1", "price?", "2026-09-25")

    assert outcome.answer.text == "second"
    notes = [s for s in outcome.trace.steps if s.detail.get("note") == "self_check_requested"]
    assert len(notes) == 1


def test_without_the_self_check_the_first_answer_is_taken(store):
    agent = agent_with(store, [call("final_answer", text="first", sources=["s"])])
    assert agent.answer("q1", "price?", "2026-09-25").answer.text == "first"


# --- state between questions ------------------------------------------------


def test_an_answer_does_not_leak_into_the_next_question(store):
    # The final-answer tool holds state, so a stale answer could be returned for
    # a question the agent never actually finished.
    agent = agent_with(
        store,
        [
            call("final_answer", text="first answer", sources=["s"]),
            "nonsense",
            "nonsense",
            "nonsense",
        ],
    )
    first = agent.answer("q1", "price?", "2026-09-25")
    second = agent.answer("q2", "another?", "2026-09-25")

    assert first.answered
    assert second.stop == "no_valid_reply"
    assert second.answer is None


# --- traces on disk ---------------------------------------------------------


def test_traces_round_trip_through_a_file(tmp_path):
    trace = Trace(question_id="q1", question="price?", model="m")
    trace.record("model", prompt_tokens=10, completion_tokens=5, latency_ms=12.5)
    trace.record("tool", tool="get_prices", ok=True, result="102.00")

    writer = TraceWriter(tmp_path / "traces.jsonl")
    writer.write(trace)

    (row,) = writer.read()
    assert row["question_id"] == "q1"
    assert row["total_tokens"] == 15
    assert len(row["steps"]) == 2


def test_completed_ids_let_a_killed_run_resume(tmp_path):
    writer = TraceWriter(tmp_path / "traces.jsonl")
    writer.write(Trace(question_id="q1"))
    writer.write(Trace(question_id="q2"))

    assert writer.completed_ids() == {"q1", "q2"}


def test_reading_a_file_that_does_not_exist_yet_gives_nothing(tmp_path):
    assert TraceWriter(tmp_path / "missing.jsonl").read() == []
