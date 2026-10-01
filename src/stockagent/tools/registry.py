"""Which tools an agent has.

The set is a configuration setting rather than a constant, because Experiment B
varies it: purpose-built tools, SQL only, retrieval only. Naming the arms here
means a run config names a tool set and the comparison is reproducible.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from stockagent.data.store import MarketStore
from stockagent.retrieval.bm25 import BM25Index
from stockagent.tools.base import Tool, ToolError, ToolResult
from stockagent.tools.calculator import CalculatorTool
from stockagent.tools.final import FinalAnswerTool
from stockagent.tools.market import ActionsTool, DividendsTool, PricesTool, ResolveTool
from stockagent.tools.search import SearchTool
from stockagent.tools.sql import SqlTool

# The named arms of the tool-design experiment.
TOOL_SETS = {
    # Everything. The agent as intended.
    "full": ("resolve_security", "get_prices", "get_dividends", "get_corporate_actions",
             "search_documents", "run_sql", "calculate"),
    # Purpose-built lookups only, no SQL. Tests whether SQL earns its place.
    "purpose_built": ("resolve_security", "get_prices", "get_dividends",
                      "get_corporate_actions", "calculate"),
    # The model writes its own queries instead.
    "sql_only": ("run_sql", "calculate"),
    # Retrieval and nothing else, which is the retrieval baseline with a loop.
    "retrieval_only": ("search_documents", "calculate"),
    # No tools at all: the closed-book baseline answers from memory.
    "none": (),
}


@dataclass
class ToolRegistry:
    """The tools available for one run, by name."""

    tools: dict[str, Tool] = field(default_factory=dict)
    final: FinalAnswerTool = field(default_factory=FinalAnswerTool)

    def add(self, tool: Tool) -> None:
        self.tools[tool.spec.name] = tool

    def names(self) -> list[str]:
        return sorted(self.tools)

    def schemas(self) -> list[dict]:
        """Tool definitions for the model, with the final answer always last.

        Ordering is stable so a cached response keyed on the request stays valid
        between runs.
        """
        ordinary = [self.tools[name].spec.as_schema() for name in self.names()]
        return [*ordinary, self.final.spec.as_schema()]

    def call(self, name: str, arguments: dict) -> ToolResult:
        """Run a tool by name, turning any failure into a result.

        A model calling a tool that does not exist, or with the wrong arguments,
        is a normal event. Raising would end the turn; a result telling it what
        went wrong lets it recover, and recovery is part of what is being
        measured.
        """
        if name == self.final.spec.name:
            target: Tool = self.final
        else:
            found = self.tools.get(name)
            if found is None:
                available = ", ".join([*self.names(), self.final.spec.name])
                return ToolResult.failure(
                    f"there is no tool called {name!r}. Available: {available}."
                )
            target = found

        if not isinstance(arguments, dict):
            return ToolResult.failure("tool arguments must be an object")

        try:
            return target.run(**arguments)
        except ToolError as error:
            return ToolResult.failure(str(error))
        except (ValueError, TypeError) as error:
            return ToolResult.failure(f"{name} could not be called: {error}")


def build_tools(
    store: MarketStore,
    *,
    index: BM25Index | None = None,
    names: Sequence[str] | str = "full",
    require_sources: bool = True,
    sql_row_limit: int = 50,
    sql_timeout_s: float = 10.0,
    calculator_timeout_s: float = 5.0,
) -> ToolRegistry:
    """Assemble a registry from a tool-set name or an explicit list."""
    wanted: Iterable[str]
    if isinstance(names, str):
        if names not in TOOL_SETS:
            raise ValueError(f"unknown tool set {names!r}; known: {', '.join(sorted(TOOL_SETS))}")
        wanted = TOOL_SETS[names]
    else:
        wanted = names

    available: dict[str, Tool] = {
        "resolve_security": ResolveTool(store),
        "get_prices": PricesTool(store),
        "get_dividends": DividendsTool(store),
        "get_corporate_actions": ActionsTool(store),
        "run_sql": SqlTool(store, row_limit=sql_row_limit, timeout_s=sql_timeout_s),
        "calculate": CalculatorTool(timeout_s=calculator_timeout_s),
    }
    if index is not None:
        available["search_documents"] = SearchTool(index)

    registry = ToolRegistry(final=FinalAnswerTool(require_sources=require_sources))
    for name in wanted:
        tool = available.get(name)
        if tool is None:
            # Asking for document search without an index is a configuration
            # mistake worth failing on, not something to skip quietly.
            raise ValueError(
                f"tool {name!r} was requested but is not available"
                + (" (no document index was given)" if name == "search_documents" else "")
            )
        registry.add(tool)
    return registry


def default_registry(store: MarketStore, index: BM25Index | None = None) -> ToolRegistry:
    return build_tools(store, index=index, names="full" if index else "purpose_built")
