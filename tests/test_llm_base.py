"""The request shape, its cache key, and the fake clients."""

import dataclasses

import pytest

from stockagent.llm.base import ChatRequest, ModelClient, system, user
from stockagent.llm.fake import FakeModelClient, FakeModelExhausted, NeverCalledClient


def request(**overrides) -> ChatRequest:
    base = {"model": "m", "messages": (system("you are terse"), user("price of AAPL?"))}
    return ChatRequest(**{**base, **overrides})


def test_cache_key_is_stable_for_the_same_request():
    assert request().cache_key() == request().cache_key()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("model", "other"),
        ("temperature", 0.7),
        ("top_p", 0.9),
        ("max_tokens", 4096),
        ("seed", 99),
        ("stop", ("\n",)),
        ("messages", (user("price of MSFT?"),)),
    ],
)
def test_every_field_changes_the_cache_key(field_name, value):
    # Two requests that differ in any way must not share a cached answer.
    assert request(**{field_name: value}).cache_key() != request().cache_key()


def test_cache_key_covers_every_field_on_the_request():
    # The parametrised test above is only as complete as its own list. This
    # checks the list against the dataclass, so a field added later fails here
    # until someone proves it changes the key too.
    covered = {"model", "temperature", "top_p", "max_tokens", "seed", "stop", "messages"}
    assert {f.name for f in dataclasses.fields(ChatRequest)} == covered


def test_last_user_message_ignores_the_system_prompt():
    assert request().last_user_message() == "price of AAPL?"


def test_last_user_message_is_empty_when_there_is_none():
    assert ChatRequest(model="m", messages=(system("hi"),)).last_user_message() == ""


def test_fake_client_satisfies_the_protocol():
    assert isinstance(FakeModelClient(), ModelClient)


def test_fake_client_returns_replies_in_order():
    client = FakeModelClient(replies=["first", "second"])
    assert client.chat(request()).text == "first"
    assert client.chat(request()).text == "second"
    assert client.call_count == 2


def test_fake_client_matches_on_the_user_message_before_the_queue():
    client = FakeModelClient(replies=["fallback"], by_substring={"MSFT": "matched"})
    assert client.chat(request(messages=(user("price of MSFT?"),))).text == "matched"
    # The queue was not touched, so it is still available for the next call.
    assert client.chat(request()).text == "fallback"


def test_fake_client_raises_when_it_runs_out():
    client = FakeModelClient(replies=["only one"])
    client.chat(request())
    with pytest.raises(FakeModelExhausted):
        client.chat(request())


def test_fake_client_records_what_it_was_asked():
    client = FakeModelClient(replies=["x"])
    client.chat(request(temperature=0.3))
    assert client.calls[0].temperature == 0.3


def test_never_called_client_fails_loudly():
    with pytest.raises(AssertionError, match="should not reach it"):
        NeverCalledClient().chat(request())
