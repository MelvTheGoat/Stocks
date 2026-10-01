"""The tool that ends the turn.

Making the final answer a tool call rather than free prose is what turns "the
model said something" into a structured record: the figure, its currency, its
as-of date and its sources arrive in named fields. That is worth a lot. A grader
can read the fields directly, a trace viewer can show them, and a missing
citation is a missing field rather than something a regular expression has to go
looking for.

It also lets the loop refuse an answer that is not ready. An answer with a figure
but no source is incomplete by construction, and saying so to the model gives it
a chance to go and find one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stockagent.tools.base import ToolResult, ToolSpec, require


@dataclass(frozen=True)
class FinalAnswer:
    """The structured answer the loop returns."""

    text: str
    sources: tuple[str, ...] = ()
    currency: str = ""
    as_of: str = ""
    # True when the agent is declining: no data, or a request for advice.
    declined: bool = False

    def rendered(self) -> str:
        """The answer as a reader would see it, with its provenance attached.

        The as-of date and the sources are appended rather than left to the
        model's prose, because every grader and every reader needs them and a
        model that forgets them half the time makes the result unusable.
        """
        parts = [self.text.strip()]
        if self.as_of:
            parts.append(f"As of {self.as_of}.")
        if self.sources:
            parts.append(f"Sources: {', '.join(self.sources)}.")
        return " ".join(part for part in parts if part)


@dataclass
class FinalAnswerTool:
    """Records the answer. Does not itself check whether it is right."""

    # Set false for the closed-book baseline, which by design has no sources.
    require_sources: bool = True
    answer: FinalAnswer | None = field(default=None, init=False)

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="final_answer",
            description=(
                "Give the final answer and end your turn. Include the figure in the "
                "answer text, the currency if the answer is an amount of money, the "
                "as-of date you are speaking about, and the sources you read. "
                "If the data does not cover the question, say so plainly and set "
                "declined to true rather than estimating. If you are being asked for "
                "investment advice, decline, set declined to true, and give the relevant "
                "figures instead."
            ),
            parameters={
                "text": {
                    "type": "string",
                    "description": "the answer in plain words, including any figure",
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "the sources you read, as returned by the tools",
                },
                "currency": {
                    "type": "string",
                    "description": "USD or NGN, if the answer is an amount of money",
                },
                "as_of": {
                    "type": "string",
                    "description": "the date the answer is true as of, YYYY-MM-DD",
                },
                "declined": {
                    "type": "boolean",
                    "description": "true if you are declining rather than answering",
                },
            },
            required=("text",),
        )

    def run(self, **arguments) -> ToolResult:
        (text,) = require(arguments, "text")

        raw_sources = arguments.get("sources") or ()
        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]
        sources = tuple(str(source) for source in raw_sources if str(source).strip())

        declined = bool(arguments.get("declined"))

        # An answer carrying a claim but nothing to back it is sent back once.
        # A declined answer needs no sources: there was nothing to read.
        if self.require_sources and not sources and not declined:
            return ToolResult.failure(
                "this answer has no sources. Cite what you read, using the source "
                "strings the tools gave you. If the data does not cover the question, "
                "set declined to true instead."
            )

        self.answer = FinalAnswer(
            text=str(text),
            sources=sources,
            currency=str(arguments.get("currency") or ""),
            as_of=str(arguments.get("as_of") or ""),
            declined=declined,
        )
        return ToolResult.success("answer recorded", sources=sources)
