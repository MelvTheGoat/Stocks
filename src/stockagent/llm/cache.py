"""A disk cache for model responses, keyed by the whole request.

GPU hours are the scarcest thing in this project: roughly 30 a week, shared
across every experiment. Re-running an eval after changing only the grading
code should cost nothing, and with this it does.

The cache is also what makes the no-GPU regression eval in CI possible. Replay
a saved cache through the real pipeline and every part except the model itself
is exercised for free.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

from stockagent.llm.base import ChatRequest, ChatResponse, ModelClient, Usage


class ResponseCache:
    """Stores responses as one small JSON file per request.

    Files are sharded into 256 directories by the first two characters of the
    key. One flat directory with tens of thousands of entries is slow to list
    and unpleasant to sync to Hugging Face.
    """

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.hits = 0
        self.misses = 0

    def path_for(self, key: str) -> Path:
        return self.directory / key[:2] / f"{key[2:]}.json"

    def get(self, key: str) -> ChatResponse | None:
        path = self.path_for(key)
        if not path.exists():
            self.misses += 1
            return None
        try:
            raw = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            # A half-written file from a killed Kaggle session. Treat it as a
            # miss and let it be overwritten, rather than failing the run.
            self.misses += 1
            return None
        self.hits += 1
        return ChatResponse(
            text=raw["text"],
            model=raw.get("model", ""),
            usage=Usage(raw.get("prompt_tokens", 0), raw.get("completion_tokens", 0)),
            # Latency belongs to the call that produced it, not to this read.
            latency_ms=0.0,
            finish_reason=raw.get("finish_reason", "stop"),
            cached=True,
        )

    def put(self, key: str, response: ChatResponse) -> None:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "text": response.text,
            "model": response.model,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "finish_reason": response.finish_reason,
            # Kept for later analysis of how long the original call took.
            "original_latency_ms": response.latency_ms,
        }
        # Write then rename. Kaggle kills the session at the time limit, and a
        # rename is atomic, so the cache can never contain a truncated entry.
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload))
        os.replace(temporary, path)

    def __len__(self) -> int:
        return sum(1 for _ in self.directory.glob("*/*.json"))


@dataclass
class CachingClient:
    """Serves a saved response when the exact request has been seen before."""

    inner: ModelClient
    cache: ResponseCache
    # Set false to force fresh calls while keeping the writes, which is how a
    # run measures real latency without throwing the cache away.
    read: bool = True
    write: bool = True

    def chat(self, request: ChatRequest) -> ChatResponse:
        key = request.cache_key()
        if self.read:
            hit = self.cache.get(key)
            if hit is not None:
                return hit
        response = self.inner.chat(request)
        if self.write:
            self.cache.put(key, response)
        return replace(response, cached=False)
