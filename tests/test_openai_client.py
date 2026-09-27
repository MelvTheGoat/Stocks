"""The HTTP client, driven through a mock transport so nothing leaves the box."""

import json

import httpx
import pytest

from stockagent.config import ModelConfig
from stockagent.llm import build_client, request_from_config
from stockagent.llm.base import (
    ChatRequest,
    PermanentModelError,
    TransientModelError,
    user,
)
from stockagent.llm.fake import FakeModelClient
from stockagent.llm.openai_client import OpenAICompatibleClient

COMPLETION = {
    "model": "served-model",
    "choices": [{"message": {"role": "assistant", "content": "241.30"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 31, "completion_tokens": 4},
}


def client_returning(handler) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(transport=httpx.MockTransport(handler), timeout_s=5.0)


def responding(status: int, json=None, text: str = "") -> OpenAICompatibleClient:
    def handler(_request):
        if json is not None:
            return httpx.Response(status, json=json)
        return httpx.Response(status, text=text)

    return client_returning(handler)


def request(**overrides) -> ChatRequest:
    base = {"model": "m", "messages": (user("price of AAPL?"),)}
    return ChatRequest(**{**base, **overrides})


def test_a_normal_completion_is_parsed():
    response = responding(200, COMPLETION).chat(request())

    assert response.text == "241.30"
    assert response.model == "served-model"
    assert response.usage.prompt_tokens == 31
    assert response.usage.total_tokens == 35
    assert response.finish_reason == "stop"
    assert response.cached is False
    assert response.latency_ms >= 0


def capture_body(seen: dict):
    def handler(http_request):
        seen.update(json.loads(http_request.content))
        return httpx.Response(200, json=COMPLETION)

    return handler


def test_the_request_body_carries_the_sampling_settings():
    seen = {}
    client = client_returning(capture_body(seen))

    client.chat(request(temperature=0.4, max_tokens=99, seed=7, stop=("\n\n",)))

    assert seen["temperature"] == 0.4
    assert seen["max_tokens"] == 99
    assert seen["seed"] == 7
    assert seen["stop"] == ["\n\n"]
    assert seen["messages"] == [{"role": "user", "content": "price of AAPL?"}]


def test_seed_is_left_out_when_it_is_none():
    seen = {}
    client_returning(capture_body(seen)).chat(request(seed=None))
    assert "seed" not in seen


def test_an_empty_content_field_is_an_empty_string_not_a_crash():
    body = {**COMPLETION, "choices": [{"message": {"content": None}, "finish_reason": "length"}]}
    response = responding(200, body).chat(request())

    assert response.text == ""
    assert response.finish_reason == "length"


def test_a_response_with_no_usage_block_still_works():
    body = {k: v for k, v in COMPLETION.items() if k != "usage"}
    assert responding(200, body).chat(request()).usage.total_tokens == 0


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_busy_and_broken_servers_are_transient(status):
    # 503 is what vLLM gives while it is still loading weights, and 429 is what
    # it gives under load. Both clear on their own.
    with pytest.raises(TransientModelError):
        responding(status, text="busy").chat(request())


@pytest.mark.parametrize("status", [400, 401, 404, 422])
def test_client_mistakes_are_permanent(status):
    # Retrying a request the server refuses to parse spends GPU budget four
    # times over to reach the same error.
    with pytest.raises(PermanentModelError):
        responding(status, text="bad request").chat(request())


def test_a_timeout_is_transient():
    def handler(_request):
        raise httpx.ReadTimeout("too slow")

    with pytest.raises(TransientModelError, match="timed out"):
        client_returning(handler).chat(request())


def test_a_refused_connection_is_transient():
    def handler(_request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(TransientModelError, match="could not reach"):
        client_returning(handler).chat(request())


def test_a_200_that_is_not_a_completion_is_permanent():
    with pytest.raises(PermanentModelError, match="unexpected response body"):
        responding(200, {"something": "else"}).chat(request())


def test_is_ready_reports_whether_the_server_answers():
    assert responding(200, {"data": []}).is_ready() is True
    assert responding(503, text="loading").is_ready() is False

    def refuse(_request):
        raise httpx.ConnectError("not up yet")

    assert client_returning(refuse).is_ready() is False


# --- the assembled stack ----------------------------------------------------


def test_build_client_caches_logs_and_retries_together(tmp_path):
    config = ModelConfig(name="m", max_retries=2)
    inner = FakeModelClient(replies=["241.30"])
    client = build_client(
        config,
        cache_dir=tmp_path / "cache",
        log_path=tmp_path / "calls.jsonl",
        run_name="smoke",
        inner=inner,
    )

    first = client.chat(request_from_config(config, (user("price of AAPL?"),)))
    second = client.chat(request_from_config(config, (user("price of AAPL?"),)))

    assert (first.text, second.text) == ("241.30", "241.30")
    # The second answer came from disk.
    assert inner.call_count == 1
    # Both are on record, so the run reports two questions answered.
    logged = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert [line["cached"] for line in logged] == [False, True]


def test_request_from_config_takes_its_settings_from_the_config():
    config = ModelConfig(name="served", temperature=0.2, top_p=0.8, max_tokens=64, seed=3)
    built = request_from_config(config, (user("hi"),))

    assert (built.model, built.temperature, built.top_p, built.max_tokens, built.seed) == (
        "served",
        0.2,
        0.8,
        64,
        3,
    )
