"""The agent loop, written from scratch.

Ask the model, read a tool call, run it, append the result, repeat until it calls
final_answer or runs out of steps. That is the whole idea; the care is in what
happens when things go wrong.

Three behaviours are worth knowing about, because each one turns a failed run
into a usable result:

**A step limit that produces an answer.** Running out of steps returns an outcome
marked `out_of_steps` rather than raising. A question the agent could not finish
is a question it got wrong, and it should be scored as such, not dropped from the
denominator. Dropping it would quietly improve the accuracy figure.

**Parse failures are coached, not fatal.** A model that emits prose instead of
JSON is told what to send instead and gets another go. The attempts are counted,
because a model needing three tries is more expensive than one needing one, and
that belongs in the comparison rather than being smoothed away.

**Tool failures are information.** "No data for that ticker" goes back to the
model as a result, giving it the chance to say so to the reader. That is the
behaviour being measured, so it must not be short-circuited.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from stockagent.agent.prompts import (
    SELF_CHECK_PROMPT,
    SYSTEM_PROMPT,
    question_prompt,
    tools_prompt,
)
from stockagent.agent.protocol import ParseFailure, ToolCall, parse_tool_call
from stockagent.agent.trace import Trace
from stockagent.llm.base import ChatRequest, Message, ModelClient, ModelError, assistant, user
from stockagent.tools.base import ToolResult
from stockagent.tools.final import FinalAnswer
from stockagent.tools.registry import ToolRegistry

Stop = Literal["answered", "out_of_steps", "model_error", "no_valid_reply"]

# How many consecutive unparseable replies to coach through before giving up. Two
# is enough to get past a stray code fence; more and the model is not going to.
MAX_PARSE_RETRIES = 2


@dataclass(frozen=True)
class _ModelFailure:
    detail: str


@dataclass
class AgentOutcome:
    """What one question produced."""

    question_id: str
    stop: Stop
    answer: FinalAnswer | None
    trace: Trace
    # Written when the loop ended without an answer, for the error analysis.
    detail: str = ""

    @property
    def answered(self) -> bool:
        return self.stop == "answered" and self.answer is not None

    def text(self) -> str:
        """The answer as a reader would see it, or the empty string.

        The graders read this, so an unanswered question grades as wrong rather
        than crashing the run.
        """
        return self.answer.rendered() if self.answer else ""


@dataclass
class Agent:
    client: ModelClient
    registry: ToolRegistry
    model: str = "local"
    max_steps: int = 8
    temperature: float = 0.0
    max_tokens: int = 512
    seed: int | None = 0
    system_prompt: str = SYSTEM_PROMPT
    # Experiment D. One extra turn telling the agent to check its own figures
    # before answering.
    self_check: bool = False
    run_name: str = ""
    _self_check_sent: bool = field(default=False, init=False)

    def answer(self, question_id: str, question: str, as_of: str) -> AgentOutcome:
        trace = Trace(
            question_id=question_id, question=question, model=self.model, run=self.run_name
        )
        # A fresh registry per question would be cleaner, but the final answer
        # tool holds state, so it is reset explicitly instead.
        self.registry.final.answer = None
        self._self_check_sent = False

        messages: list[Message] = [
            user(
                f"{tools_prompt(self.registry.schemas())}\n\n"
                f"{question_prompt(question, as_of)}"
            )
        ]

        parse_failures = 0

        for _ in range(self.max_steps):
            reply = self._ask(messages, trace)
            if isinstance(reply, _ModelFailure):
                return AgentOutcome(question_id, "model_error", None, trace, detail=reply.detail)

            messages.append(assistant(reply))
            parsed = parse_tool_call(reply)

            if isinstance(parsed, ParseFailure):
                parse_failures += 1
                trace.record(
                    "error",
                    problem="parse_failure",
                    reason=parsed.reason,
                    attempt=parse_failures,
                    reply=reply[:400],
                )
                if parse_failures > MAX_PARSE_RETRIES:
                    return AgentOutcome(
                        question_id,
                        "no_valid_reply",
                        None,
                        trace,
                        detail=f"{parse_failures} unparseable replies: {parsed.reason}",
                    )
                messages.append(user(parsed.guidance))
                continue

            parse_failures = 0
            result = self._run_tool(parsed, trace)

            if parsed.tool == self.registry.final.spec.name and result.ok:
                answer = self.registry.final.answer
                if self.self_check and not self._self_check_sent:
                    # One nudge, then accept whatever comes back. Repeating it
                    # would be a different experiment.
                    self._self_check_sent = True
                    self.registry.final.answer = None
                    trace.record("note", note="self_check_requested")
                    messages.append(user(SELF_CHECK_PROMPT))
                    continue
                trace.record("answer", text=answer.text, sources=list(answer.sources),
                             declined=answer.declined)
                return AgentOutcome(question_id, "answered", answer, trace)

            messages.append(user(self._format_result(parsed, result)))

        # Out of steps. Scored as wrong, not dropped: dropping it would quietly
        # improve the accuracy figure by removing the hard questions.
        return AgentOutcome(
            question_id,
            "out_of_steps",
            None,
            trace,
            detail=f"did not call final_answer within {self.max_steps} steps",
        )

    # --- the two halves of a step ------------------------------------------

    def _ask(self, messages: list[Message], trace: Trace):
        request = ChatRequest(
            model=self.model,
            messages=(Message(role="system", content=self.system_prompt), *messages),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            seed=self.seed,
        )
        started = time.perf_counter()
        try:
            response = self.client.chat(request)
        except ModelError as error:
            trace.record(
                "error",
                problem="model_error",
                error=type(error).__name__,
                message=str(error)[:300],
                latency_ms=(time.perf_counter() - started) * 1000,
            )
            return _ModelFailure(detail=f"{type(error).__name__}: {error}")

        trace.record(
            "model",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            latency_ms=response.latency_ms,
            cached=response.cached,
            reply=response.text[:2000],
            finish_reason=response.finish_reason,
        )
        return response.text

    def _run_tool(self, call: ToolCall, trace: Trace) -> ToolResult:
        started = time.perf_counter()
        result = self.registry.call(call.tool, call.arguments)
        trace.record(
            "tool",
            tool=call.tool,
            arguments=call.arguments,
            thought=call.thought[:300],
            ok=result.ok,
            result=result.content[:2000],
            sources=list(result.sources),
            latency_ms=(time.perf_counter() - started) * 1000,
        )
        return result

    @staticmethod
    def _format_result(call: ToolCall, result: ToolResult) -> str:
        status = "result" if result.ok else "error"
        return f"{call.tool} {status}:\n{result.content}"

