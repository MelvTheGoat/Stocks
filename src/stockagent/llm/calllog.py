"""A line of JSON for every model call.

Token counts and latency are results in their own right in this project:
Experiment C compares model sizes on accuracy against cost and latency, and
that comparison is only as good as the measurement underneath it. So every
call is recorded, including the ones served from cache and the ones that
failed.

The file is JSONL -- one JSON object per line -- because it can be appended to
safely and read back even if a run is killed halfway through.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from stockagent.llm.base import ChatRequest, ChatResponse, ModelClient, ModelError


class CallLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: dict) -> None:
        with self.path.open("a") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]


@dataclass
class LoggingClient:
    """Wraps a client and records what every call cost.

    Sits outermost, above the cache, so a cache hit is logged as a call that
    took no GPU time rather than not logged at all. Counting only the misses
    would make a re-run look free and a first run look expensive, when the
    honest statement is that both answered the same number of questions.
    """

    inner: ModelClient
    log: CallLog
    # Written onto every record so calls can be grouped by run afterwards.
    run_name: str = ""

    def chat(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        base = {
            "run": self.run_name,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "model": request.model,
            "request_key": request.cache_key()[:16],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        try:
            response = self.inner.chat(request)
        except ModelError as error:
            self.log.write(
                {
                    **base,
                    "ok": False,
                    "error": type(error).__name__,
                    "message": str(error)[:300],
                    "observed_latency_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )
            raise
        self.log.write(
            {
                **base,
                "ok": True,
                "cached": response.cached,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "finish_reason": response.finish_reason,
                # What the caller waited. Near zero on a cache hit, which is
                # why `cached` sits beside it.
                "observed_latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
        return response
