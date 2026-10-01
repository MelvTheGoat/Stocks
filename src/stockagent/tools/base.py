"""What a tool is.

A tool has a name, a description the model reads, a parameter schema, and a
`run` method returning a `ToolResult`. Nothing more. Keeping the surface this
small is what allows the agent loop to be written once and the tool set to be
varied as an experiment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class ToolError(Exception):
    """A tool was called in a way that cannot be turned into a result."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    # Written for the model, not for a developer. It has to say what the tool
    # gives back and what it will refuse, because an agent that cannot predict a
    # refusal wastes steps discovering it.
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()

    def as_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": list(self.required),
            },
        }


@dataclass(frozen=True)
class ToolResult:
    """What a tool hands back to the loop.

    `content` is what the model sees, so it is prose or a small table rather than
    a serialised object. `sources` is what a citation would point at, collected
    by the loop so the final answer can be checked for grounding.
    """

    ok: bool
    content: str
    sources: tuple[str, ...] = ()
    # Set when a tool declined. Kept separate from `content` so the loop can
    # count failures without parsing text.
    error: str = ""
    # Anything the loop or a test needs that the model does not, such as the
    # number of rows behind a summary.
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def failure(cls, error: str) -> ToolResult:
        return cls(ok=False, content=error, error=error)

    @classmethod
    def success(cls, content: str, sources: tuple[str, ...] = (), **meta: Any) -> ToolResult:
        return cls(ok=True, content=content, sources=sources, meta=meta)


@runtime_checkable
class Tool(Protocol):
    @property
    def spec(self) -> ToolSpec: ...

    def run(self, **arguments: Any) -> ToolResult: ...


def require(arguments: dict[str, Any], *names: str) -> list[Any]:
    """Pull required arguments out, or raise with a message the model can use."""
    missing = [name for name in names if arguments.get(name) in (None, "")]
    if missing:
        raise ToolError(f"missing required argument(s): {', '.join(missing)}")
    return [arguments[name] for name in names]
