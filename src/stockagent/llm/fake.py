"""Model clients for tests. These never open a socket.

Two of them, for two different jobs:

`FakeModelClient` returns replies you scripted, and records what it was asked.
Use it to drive the agent loop, the graders and the parsers through known
inputs.

`NeverCalledClient` raises if anything calls it at all. Use it to prove a path
does *not* reach the model -- a cached answer, a refused question, a query with
no data behind it. A test that asserts on an output cannot tell you whether the
GPU was touched on the way; this can.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stockagent.llm.base import ChatRequest, ChatResponse, ModelError, Usage


class FakeModelExhausted(ModelError):
    """The fake ran out of scripted replies.

    Raised rather than looping or returning something bland, because a silent
    fallback turns "the agent took an extra step I did not expect" into a
    passing test.
    """


@dataclass
class FakeModelClient:
    """Returns scripted replies in order, or by matching the user's message.

    `replies` is consumed one call at a time. `by_substring` is checked first:
    if any of its keys appear in the last user message, its value is returned
    and the queue is left alone. That matters for an agent loop, where the
    order of calls is exactly the thing under test and hard-coding a sequence
    would assume the answer.
    """

    replies: list[str] = field(default_factory=list)
    by_substring: dict[str, str] = field(default_factory=dict)
    prompt_tokens: int = 10
    completion_tokens: int = 5
    latency_ms: float = 1.0

    calls: list[ChatRequest] = field(default_factory=list, init=False)

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.calls.append(request)
        text = self._pick(request)
        return ChatResponse(
            text=text,
            model=request.model,
            usage=Usage(self.prompt_tokens, self.completion_tokens),
            latency_ms=self.latency_ms,
        )

    def _pick(self, request: ChatRequest) -> str:
        haystack = request.last_user_message()
        for needle, reply in self.by_substring.items():
            if needle in haystack:
                return reply
        if self.replies:
            return self.replies.pop(0)
        raise FakeModelExhausted(
            f"no scripted reply left for call {len(self.calls)}; "
            f"last user message began: {haystack[:120]!r}"
        )

    @property
    def call_count(self) -> int:
        return len(self.calls)


class NeverCalledClient:
    """Fails the test if the model is called at all."""

    def chat(self, request: ChatRequest) -> ChatResponse:
        raise AssertionError(
            "the model was called on a path that should not reach it; "
            f"user message began: {request.last_user_message()[:120]!r}"
        )
