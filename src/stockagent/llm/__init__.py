"""Model client, and the wrappers that make it usable in a run.

`build_client` stacks them in the order that matters:

    logging -> cache -> retries -> HTTP

Retries sit innermost, so a call that fails twice and succeeds is cached once
and logged once. Logging sits outermost, so a cache hit is still counted as a
question answered.
"""

from __future__ import annotations

from pathlib import Path

from stockagent.config import ModelConfig
from stockagent.llm.base import (
    ChatRequest,
    ChatResponse,
    Message,
    ModelClient,
    ModelError,
    PermanentModelError,
    TransientModelError,
    Usage,
    assistant,
    system,
    user,
)
from stockagent.llm.cache import CachingClient, ResponseCache
from stockagent.llm.calllog import CallLog, LoggingClient
from stockagent.llm.fake import FakeModelClient, NeverCalledClient
from stockagent.llm.openai_client import OpenAICompatibleClient
from stockagent.llm.retry import RetryingClient

__all__ = [
    "CachingClient",
    "CallLog",
    "ChatRequest",
    "ChatResponse",
    "FakeModelClient",
    "LoggingClient",
    "Message",
    "ModelClient",
    "ModelError",
    "NeverCalledClient",
    "OpenAICompatibleClient",
    "PermanentModelError",
    "ResponseCache",
    "RetryingClient",
    "TransientModelError",
    "Usage",
    "assistant",
    "build_client",
    "request_from_config",
    "system",
    "user",
]


def build_client(
    config: ModelConfig,
    *,
    cache_dir: str | Path | None = None,
    log_path: str | Path | None = None,
    run_name: str = "",
    inner: ModelClient | None = None,
) -> ModelClient:
    """Assemble the client stack for a run.

    `inner` replaces the HTTP layer, which is how the no-GPU regression eval
    runs the whole pipeline against a fake model.
    """
    client: ModelClient = inner or OpenAICompatibleClient(
        base_url=config.endpoint, timeout_s=config.timeout_s
    )
    client = RetryingClient(client, max_retries=config.max_retries)
    if cache_dir is not None:
        client = CachingClient(client, ResponseCache(cache_dir))
    if log_path is not None:
        client = LoggingClient(client, CallLog(log_path), run_name=run_name)
    return client


def request_from_config(config: ModelConfig, messages: tuple[Message, ...]) -> ChatRequest:
    """Build a request whose sampling settings come from the run config.

    Nothing should construct a `ChatRequest` with hand-written sampling
    settings. If it did, the config file would no longer describe the run, and
    the cache key would stop matching what the config says was asked.
    """
    return ChatRequest(
        model=config.name,
        messages=messages,
        temperature=config.temperature,
        top_p=config.top_p,
        max_tokens=config.max_tokens,
        seed=config.seed,
    )
