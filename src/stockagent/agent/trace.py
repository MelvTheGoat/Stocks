"""A record of everything the agent did, one JSON object per line.

Traces are the primary evidence in this project. The error analysis in Phase 9
sorts failures into types, and the only way to tell a wrong ticker from a wrong
date from an arithmetic slip is to read what the agent actually did. A score with
no trace behind it is an assertion.

They also carry the cost measurements. Tokens and latency per step are what
Experiment C compares between model sizes, so they are recorded per call rather
than totalled at the end.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

StepKind = Literal["model", "tool", "answer", "error", "note"]


@dataclass
class TraceStep:
    index: int
    kind: StepKind
    # For a model step: what was sent and what came back. For a tool step: the
    # call and its result.
    detail: dict[str, Any] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": round(self.latency_ms, 2),
            "cached": self.cached,
            **self.detail,
        }


@dataclass
class Trace:
    """One question's worth of steps."""

    question_id: str
    question: str = ""
    model: str = ""
    run: str = ""
    steps: list[TraceStep] = field(default_factory=list)

    def record(
        self,
        kind: StepKind,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float = 0.0,
        cached: bool = False,
        **detail: Any,
    ) -> TraceStep:
        step = TraceStep(
            index=len(self.steps),
            kind=kind,
            detail=detail,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cached=cached,
        )
        self.steps.append(step)
        return step

    # --- totals, which are results in their own right ----------------------

    @property
    def model_calls(self) -> int:
        return sum(1 for step in self.steps if step.kind == "model")

    @property
    def tool_calls(self) -> int:
        return sum(1 for step in self.steps if step.kind == "tool")

    @property
    def prompt_tokens(self) -> int:
        return sum(step.prompt_tokens for step in self.steps)

    @property
    def completion_tokens(self) -> int:
        return sum(step.completion_tokens for step in self.steps)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def latency_ms(self) -> float:
        return sum(step.latency_ms for step in self.steps)

    @property
    def cache_hits(self) -> int:
        return sum(1 for step in self.steps if step.cached)

    def tools_used(self) -> list[str]:
        """Tool names in the order first called, for the error analysis."""
        seen: list[str] = []
        for step in self.steps:
            name = step.detail.get("tool")
            if step.kind == "tool" and name and name not in seen:
                seen.append(name)
        return seen

    def failed_tool_calls(self) -> int:
        return sum(
            1 for step in self.steps if step.kind == "tool" and step.detail.get("ok") is False
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "model": self.model,
            "run": self.run,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": round(self.latency_ms, 2),
            "steps": [step.to_json() for step in self.steps],
        }


class TraceWriter:
    """Appends whole traces to a JSONL file.

    One line per question rather than per step, so a killed run leaves a file of
    complete traces rather than a half-written one, and resuming is a matter of
    reading back which question ids are already there.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, trace: Trace) -> None:
        with self.path.open("a") as handle:
            handle.write(json.dumps(trace.to_json(), sort_keys=True) + "\n")

    def write_all(self, traces: Iterable[Trace]) -> None:
        for trace in traces:
            self.write(trace)

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line) for line in self.path.read_text().splitlines() if line.strip()
        ]

    def completed_ids(self) -> set[str]:
        """Questions already traced, so a resumed run skips them."""
        return {row.get("question_id", "") for row in self.read()} - {""}
