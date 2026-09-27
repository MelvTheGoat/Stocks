"""Talks to an OpenAI-compatible chat endpoint.

vLLM serves one of these, so the same client works against vLLM on Kaggle and
against anything else that speaks the same shape. "OpenAI-compatible" just
means the server accepts a POST to /v1/chat/completions with a list of
messages and returns a choice with a message in it.

The one job that needs care here is deciding which failures are worth
retrying. Getting that wrong is expensive in both directions: retrying a bad
request wastes the weekly GPU budget, and not retrying a 503 throws away an
eval run because the server was starting up.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from stockagent.llm.base import (
    ChatRequest,
    ChatResponse,
    PermanentModelError,
    TransientModelError,
    Usage,
)


@dataclass
class OpenAICompatibleClient:
    base_url: str = "http://localhost:8000/v1"
    timeout_s: float = 120.0
    # vLLM does not check this unless it was started with --api-key, but the
    # header has to be present for some proxies.
    api_key: str = "local"
    # Injected by tests so nothing opens a socket.
    transport: httpx.BaseTransport | None = None
    _client: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url.rstrip("/"),
            timeout=self.timeout_s,
            transport=self.transport,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def chat(self, request: ChatRequest) -> ChatResponse:
        payload = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_tokens,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.stop:
            payload["stop"] = list(request.stop)

        started = time.perf_counter()
        try:
            response = self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as error:
            raise TransientModelError(f"timed out after {self.timeout_s}s: {error}") from error
        except httpx.TransportError as error:
            # Connection refused while vLLM is still loading weights, or the
            # link dropped mid-request. Both are worth another go.
            raise TransientModelError(f"could not reach {self.base_url}: {error}") from error
        latency_ms = (time.perf_counter() - started) * 1000

        self._raise_for_status(response)

        try:
            body = response.json()
            choice = body["choices"][0]
            text = choice["message"]["content"] or ""
        except (ValueError, KeyError, IndexError) as error:
            # A 200 whose body is not a chat completion means the server is
            # broken or something else is listening on the port. Sending the
            # same request again gets the same nonsense back.
            raise PermanentModelError(
                f"unexpected response body from {self.base_url}: {error}"
            ) from error

        usage = body.get("usage") or {}
        return ChatResponse(
            text=text,
            model=body.get("model", request.model),
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            ),
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason") or "stop",
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        detail = response.text[:300]
        # 429 means slow down, 5xx means the server is unwell or still warming
        # up. Everything else in the 4xx range is our own mistake.
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientModelError(f"HTTP {response.status_code}: {detail}")
        raise PermanentModelError(f"HTTP {response.status_code}: {detail}")

    def is_ready(self) -> bool:
        """True once the server answers. Used while waiting for vLLM to load."""
        try:
            return self._client.get("/models").status_code == 200
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        self._client.close()
