"""Reading a tool call out of what the model wrote.

The agent speaks to the model in JSON, not through a provider's tool-calling
feature. That is a deliberate choice: vLLM's support for tool calling varies by
model and by version, and this project has to compare several models on a free
GPU. A plain JSON protocol works with any instruct model and makes the trace
readable, at the cost of having to parse tolerantly.

Tolerantly is the operative word. Open models wrap JSON in markdown fences,
preface it with "Sure, here's the tool call:", and append an explanation
afterwards. A strict parser rejects all of that and scores a model badly for
being chatty rather than for being wrong, which would make the whole comparison
measure the wrong thing. So the parser finds the first balanced JSON object in
the text and works from there.

What it does *not* do is guess at intent. A reply with no JSON object in it is a
parse failure, reported back to the model so it can try again, and counted. The
count matters: a model that needs three attempts to emit valid JSON is more
expensive than one that does it first time, and that belongs in the results.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# Strips a ```json fence, which most instruct models add unprompted.
_FENCE = re.compile(r"^\s*```(?:json|JSON)?\s*|\s*```\s*$")


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    # Whatever the model said alongside the call. Kept for the trace, not acted
    # on.
    thought: str = ""


@dataclass(frozen=True)
class ParseFailure:
    reason: str
    # A message written for the model, telling it exactly what to do differently.
    guidance: str


def find_json_object(text: str) -> str | None:
    """The first balanced {...} in the text, ignoring braces inside strings."""
    if not text:
        return None
    stripped = _FENCE.sub("", text)
    start = stripped.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for position in range(start, len(stripped)):
        character = stripped[position]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : position + 1]
    return None


RETRY_GUIDANCE = (
    'Reply with one JSON object and nothing else, in the form '
    '{"thought": "why", "tool": "tool_name", "arguments": {...}}. '
    "Do not wrap it in a code fence or add any text around it."
)


def parse_tool_call(text: str) -> ToolCall | ParseFailure:
    """Read a tool call, or explain why it could not be read."""
    candidate = find_json_object(text)
    if candidate is None:
        return ParseFailure(
            reason="no JSON object found",
            guidance=f"I could not find a JSON object in that reply. {RETRY_GUIDANCE}",
        )

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as error:
        return ParseFailure(
            reason=f"invalid JSON: {error.msg}",
            guidance=f"That JSON could not be parsed ({error.msg}). {RETRY_GUIDANCE}",
        )

    if not isinstance(payload, dict):
        return ParseFailure(
            reason="JSON was not an object",
            guidance=f"That was a {type(payload).__name__}, not an object. {RETRY_GUIDANCE}",
        )

    tool = payload.get("tool") or payload.get("name") or payload.get("tool_name")
    if not isinstance(tool, str) or not tool.strip():
        return ParseFailure(
            reason="no tool named",
            guidance=f'The object needs a "tool" field naming the tool. {RETRY_GUIDANCE}',
        )

    arguments = payload.get("arguments")
    if arguments is None:
        arguments = payload.get("args") or payload.get("input") or {}
    if isinstance(arguments, str):
        # Some models double-encode the arguments as a JSON string.
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return ParseFailure(
                reason="arguments were a string that is not JSON",
                guidance=(
                    'The "arguments" field must be an object, not a string. ' + RETRY_GUIDANCE
                ),
            )
    if not isinstance(arguments, dict):
        return ParseFailure(
            reason=f"arguments were a {type(arguments).__name__}",
            guidance=f'The "arguments" field must be an object. {RETRY_GUIDANCE}',
        )

    thought = payload.get("thought") or payload.get("reasoning") or ""
    return ToolCall(
        tool=tool.strip(), arguments=arguments, thought=str(thought) if thought else ""
    )
