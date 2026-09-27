"""The shape of a model call, and the errors one can fail with.

Everything that talks to a language model in this project goes through
`ModelClient`. Tests get a fake one, the GPU box gets a real one, and the code
in between cannot tell the difference. That is what lets the whole pipeline run
in CI with no GPU and no network.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]


class ModelError(Exception):
    """Any failure from a model call."""


class TransientModelError(ModelError):
    """Worth retrying: a timeout, a dropped connection, a 429 or a 5xx.

    The server is busy or briefly unreachable. The same request sent again may
    well succeed.
    """


class PermanentModelError(ModelError):
    """Not worth retrying: a malformed request, an unknown model, a 4xx.

    Sending it again produces the same failure, so retrying only wastes the
    GPU time budget.
    """


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class ChatRequest:
    """One call to the model, and everything that decides its answer."""

    model: str
    messages: tuple[Message, ...]
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 512
    seed: int | None = 0
    stop: tuple[str, ...] = ()

    def cache_key(self) -> str:
        """Stable hash of the entire request.

        Built from `dataclasses.asdict` rather than a hand-written list of
        fields, so a field added later is part of the key automatically. A
        hand-written key is a bug waiting for the day someone adds a sampling
        setting and forgets to list it: from then on the cache serves answers
        generated under different settings, and no test would catch it.
        """
        canonical = json.dumps(
            dataclasses.asdict(self), sort_keys=True, separators=(",", ":"), default=str
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def last_user_message(self) -> str:
        for message in reversed(self.messages):
            if message.role == "user":
                return message.content
        return ""


@dataclass(frozen=True)
class ChatResponse:
    text: str
    model: str = ""
    usage: Usage = field(default_factory=Usage)
    # Wall-clock time for the call. Zero for a cache hit, which is the point of
    # recording `cached` alongside it: a median latency that quietly includes
    # cache hits is not a latency anyone can act on.
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    cached: bool = False


@runtime_checkable
class ModelClient(Protocol):
    def chat(self, request: ChatRequest) -> ChatResponse: ...


def user(content: str) -> Message:
    return Message(role="user", content=content)


def system(content: str) -> Message:
    return Message(role="system", content=content)


def assistant(content: str) -> Message:
    return Message(role="assistant", content=content)
