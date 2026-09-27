"""Run configuration.

One run is defined by one YAML file and nothing else. Anything that could
change a result -- which model, which sampling settings, which eval set, which
agent -- lives in that file. A result then records the file it came from, so
re-running it later is a matter of pointing at the same config.

Unknown keys are rejected rather than ignored. A typo like `temparature: 0.7`
would otherwise leave the real temperature at its default while the config file
claims otherwise, and every number produced under it would be quietly
mislabelled. That is the kind of error that survives all the way into a report.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

# Rejecting unknown keys is the whole point, so every model in this file shares
# these settings.
_STRICT = ConfigDict(extra="forbid")


class ModelConfig(BaseModel):
    """Which model to call, and how.

    `name` is the name sent in the API request. vLLM serves a model under the
    Hugging Face repo id unless told otherwise, so the two are usually equal,
    but keeping them separate means a served alias does not silently become
    part of the reproducibility record.
    """

    model_config = _STRICT

    name: str
    hf_repo: str | None = None
    # T4 GPUs have no bfloat16, so float16 is the default here rather than
    # "auto". Quantised weights (AWQ or GPTQ) are what make a 7B-class model
    # fit in 16 GB alongside its KV cache.
    quantization: Literal["awq", "gptq", "none"] = "none"
    dtype: Literal["float16", "bfloat16", "auto"] = "float16"
    max_model_len: int = 4096
    gpu_memory_utilization: float = 0.90

    endpoint: str = "http://localhost:8000/v1"

    # Greedy by default. An eval that moves when nothing changed is an eval
    # that cannot measure a small improvement.
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 512
    seed: int | None = 0

    timeout_s: float = 120.0
    max_retries: int = 4


class EvalConfig(BaseModel):
    """Which questions to ask, and how to score them."""

    model_config = _STRICT

    # "dev" while improving, "test" only at the very end, "hard" for the
    # hand-checked document questions.
    split: Literal["dev", "test", "hard"] = "dev"
    version: str
    # Every eval version freezes an as-of date, so a question like "what did it
    # return this year" has one correct answer forever.
    as_of: str
    markets: list[Literal["US", "NGX"]] = Field(default_factory=lambda: ["US", "NGX"])
    limit: int | None = None
    graders: list[str] = Field(default_factory=lambda: ["numeric", "exact", "source"])


class AgentConfig(BaseModel):
    """Which system is answering."""

    model_config = _STRICT

    # closed_book and retrieval are the two baselines; agent is the real thing.
    kind: Literal["closed_book", "retrieval", "agent"]
    max_steps: int = 8
    tools: list[str] = Field(default_factory=list)
    # The extra pass where the agent re-checks its own numbers before
    # answering. Experiment D measures whether it pays for itself.
    self_check: bool = False


class RunConfig(BaseModel):
    """A complete, re-runnable description of one job."""

    model_config = _STRICT

    name: str
    description: str = ""
    model: ModelConfig
    eval: EvalConfig
    agent: AgentConfig
    seed: int = 0

    @classmethod
    def from_yaml(cls, path: str | Path) -> RunConfig:
        path = Path(path)
        with path.open() as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            raise ValueError(f"{path} should contain a YAML mapping, got {type(raw).__name__}")
        return cls.model_validate(raw)

    def fingerprint(self) -> str:
        """Short stable hash of the whole config.

        Written next to every result. If two results disagree, the first
        question is whether they were produced by the same config, and this
        answers it without a diff.
        """
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:12]
