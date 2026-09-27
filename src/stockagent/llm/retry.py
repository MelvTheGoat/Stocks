"""Retries with exponential backoff, for the failures worth retrying.

A vLLM server under load returns 429s, and a Kaggle notebook's connection to it
drops occasionally. Those are worth another attempt. A malformed request is
not: retrying it burns the GPU budget four times to reach the same error.
`TransientModelError` and `PermanentModelError` draw that line, and this class
respects it.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from stockagent.llm.base import ChatRequest, ChatResponse, ModelClient, TransientModelError


@dataclass
class RetryingClient:
    inner: ModelClient
    max_retries: int = 4
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    # Injected so tests do not actually wait, and so backoff timing can be
    # asserted on rather than guessed at.
    sleep: Callable[[float], None] = time.sleep
    rng: random.Random = field(default_factory=random.Random)

    def chat(self, request: ChatRequest) -> ChatResponse:
        last_error: TransientModelError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self.inner.chat(request)
            except TransientModelError as error:
                last_error = error
                if attempt == self.max_retries:
                    break
                self.sleep(self.delay_for(attempt))
        assert last_error is not None
        raise last_error

    def delay_for(self, attempt: int) -> float:
        """Exponential backoff with jitter, capped.

        The jitter matters when several requests fail at the same moment:
        without it they all come back at the same moment too, and the server
        that was overloaded gets the same burst again.
        """
        ceiling = min(self.base_delay_s * (2**attempt), self.max_delay_s)
        return ceiling * (0.5 + 0.5 * self.rng.random())
