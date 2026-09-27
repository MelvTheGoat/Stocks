"""Cache, retries and call logging."""

import json

import pytest

from stockagent.llm.base import (
    ChatRequest,
    ChatResponse,
    PermanentModelError,
    TransientModelError,
    Usage,
    user,
)
from stockagent.llm.cache import CachingClient, ResponseCache
from stockagent.llm.calllog import CallLog, LoggingClient
from stockagent.llm.fake import FakeModelClient, NeverCalledClient
from stockagent.llm.retry import RetryingClient


def request(text: str = "price of AAPL?") -> ChatRequest:
    return ChatRequest(model="m", messages=(user(text),))


class FlakyClient:
    """Fails a set number of times, then succeeds."""

    def __init__(self, failures: int, error=TransientModelError):
        self.remaining = failures
        self.error = error
        self.attempts = 0

    def chat(self, request):
        self.attempts += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise self.error("server busy")
        return ChatResponse(text="ok", model=request.model)


# --- cache ------------------------------------------------------------------


def test_cache_returns_nothing_when_empty(tmp_path):
    assert ResponseCache(tmp_path).get("abc123") is None


def test_cache_round_trips_text_and_tokens(tmp_path):
    cache = ResponseCache(tmp_path)
    cache.put("abc123", ChatResponse(text="hello", model="m", usage=Usage(7, 3)))

    got = cache.get("abc123")
    assert got.text == "hello"
    assert got.usage.prompt_tokens == 7
    assert got.usage.total_tokens == 10


def test_a_cached_response_is_marked_cached_and_carries_no_latency(tmp_path):
    cache = ResponseCache(tmp_path)
    cache.put("abc123", ChatResponse(text="hello", latency_ms=980.0))

    got = cache.get("abc123")
    assert got.cached is True
    # The 980ms belonged to the original call, not to reading a file.
    assert got.latency_ms == 0.0


def test_a_corrupt_cache_file_reads_as_a_miss(tmp_path):
    # What a Kaggle session killed mid-write leaves behind.
    cache = ResponseCache(tmp_path)
    path = cache.path_for("abc123")
    path.parent.mkdir(parents=True)
    path.write_text('{"text": "trunca')

    assert cache.get("abc123") is None


def test_second_identical_call_never_reaches_the_model(tmp_path):
    inner = FakeModelClient(replies=["generated once"])
    client = CachingClient(inner, ResponseCache(tmp_path))

    first = client.chat(request())
    assert first.cached is False
    assert inner.call_count == 1

    # The fake has no replies left, so a second call reaching it would raise.
    second = client.chat(request())
    assert second.text == "generated once"
    assert second.cached is True
    assert inner.call_count == 1


def test_a_different_request_is_a_different_entry(tmp_path):
    inner = FakeModelClient(replies=["about apple", "about microsoft"])
    client = CachingClient(inner, ResponseCache(tmp_path))

    assert client.chat(request("price of AAPL?")).text == "about apple"
    assert client.chat(request("price of MSFT?")).text == "about microsoft"


def test_cache_survives_being_reopened(tmp_path):
    CachingClient(FakeModelClient(replies=["once"]), ResponseCache(tmp_path)).chat(request())

    # A fresh process, a fresh cache object, the same directory. Nothing may
    # reach the model.
    reopened = CachingClient(NeverCalledClient(), ResponseCache(tmp_path))
    assert reopened.chat(request()).text == "once"


def test_reads_can_be_turned_off_while_still_writing(tmp_path):
    cache = ResponseCache(tmp_path)
    CachingClient(FakeModelClient(replies=["stale"]), cache).chat(request())

    fresh = CachingClient(FakeModelClient(replies=["fresh"]), cache, read=False)
    assert fresh.chat(request()).text == "fresh"
    assert cache.get(request().cache_key()).text == "fresh"


def test_cache_counts_hits_and_misses(tmp_path):
    cache = ResponseCache(tmp_path)
    client = CachingClient(FakeModelClient(replies=["x"]), cache)
    client.chat(request())
    client.chat(request())

    assert (cache.misses, cache.hits) == (1, 1)


# --- retries ----------------------------------------------------------------


def test_a_transient_failure_is_retried_until_it_succeeds():
    inner = FlakyClient(failures=2)
    client = RetryingClient(inner, max_retries=4, sleep=lambda _: None)

    assert client.chat(request()).text == "ok"
    assert inner.attempts == 3


def test_retries_give_up_and_raise_after_the_limit():
    inner = FlakyClient(failures=99)
    client = RetryingClient(inner, max_retries=2, sleep=lambda _: None)

    with pytest.raises(TransientModelError):
        client.chat(request())
    # One first try plus two retries.
    assert inner.attempts == 3


def test_a_permanent_failure_is_not_retried():
    inner = FlakyClient(failures=99, error=PermanentModelError)
    client = RetryingClient(inner, max_retries=4, sleep=lambda _: None)

    with pytest.raises(PermanentModelError):
        client.chat(request())
    assert inner.attempts == 1


def test_a_successful_call_never_sleeps():
    slept = []
    RetryingClient(FakeModelClient(replies=["ok"]), sleep=slept.append).chat(request())
    assert slept == []


def test_backoff_grows_and_is_capped():
    client = RetryingClient(FakeModelClient(), base_delay_s=1.0, max_delay_s=10.0)
    delays = [client.delay_for(attempt) for attempt in range(6)]

    # Jitter makes each delay a range, so assert on the range not the value.
    assert 0.5 <= delays[0] <= 1.0
    assert 2.0 <= delays[2] <= 4.0
    assert all(delay <= 10.0 for delay in delays)


def test_jitter_spreads_retries_out():
    client = RetryingClient(FakeModelClient(), base_delay_s=8.0)
    assert len({client.delay_for(3) for _ in range(20)}) > 1


# --- call logging -----------------------------------------------------------


def test_every_call_is_logged_with_its_tokens_and_latency(tmp_path):
    log = CallLog(tmp_path / "calls.jsonl")
    client = LoggingClient(FakeModelClient(replies=["hi"]), log, run_name="smoke")

    client.chat(request())

    (record,) = log.read()
    assert record["run"] == "smoke"
    assert record["ok"] is True
    assert record["prompt_tokens"] == 10
    assert record["completion_tokens"] == 5
    assert record["total_tokens"] == 15
    assert record["observed_latency_ms"] >= 0


def test_cache_hits_are_logged_too_and_marked_as_such(tmp_path):
    log = CallLog(tmp_path / "calls.jsonl")
    cached = CachingClient(FakeModelClient(replies=["hi"]), ResponseCache(tmp_path / "c"))
    client = LoggingClient(cached, log)

    client.chat(request())
    client.chat(request())

    # Two questions were answered, so two calls are on record, and the second
    # is visibly the free one.
    assert [r["cached"] for r in log.read()] == [False, True]


def test_a_failed_call_is_logged_and_still_raises(tmp_path):
    log = CallLog(tmp_path / "calls.jsonl")
    client = LoggingClient(FlakyClient(failures=1), log)

    with pytest.raises(TransientModelError):
        client.chat(request())

    (record,) = log.read()
    assert record["ok"] is False
    assert record["error"] == "TransientModelError"


def test_the_log_is_one_json_object_per_line(tmp_path):
    path = tmp_path / "calls.jsonl"
    client = LoggingClient(FakeModelClient(replies=["a", "b"]), CallLog(path))
    client.chat(request("one"))
    client.chat(request("two"))

    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["ok"] for line in lines)
