"""The tools the agent can call.

Every tool returns a `ToolResult` rather than raising, because a tool failing is
an ordinary event in an agent loop and the model needs to be told about it in a
form it can act on. An exception would end the turn; a result saying "no data for
that ticker" lets the agent say so to the reader, which is the behaviour being
measured.
"""

from stockagent.tools.base import Tool, ToolError, ToolResult, ToolSpec
from stockagent.tools.calculator import CalculatorTool
from stockagent.tools.final import FinalAnswer, FinalAnswerTool
from stockagent.tools.market import (
    ActionsTool,
    DividendsTool,
    PricesTool,
    ResolveTool,
)
from stockagent.tools.registry import TOOL_SETS, ToolRegistry, build_tools, default_registry
from stockagent.tools.search import SearchTool
from stockagent.tools.sql import SqlTool

__all__ = [
    "ActionsTool",
    "CalculatorTool",
    "DividendsTool",
    "FinalAnswer",
    "FinalAnswerTool",
    "PricesTool",
    "ResolveTool",
    "SearchTool",
    "SqlTool",
    "Tool",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "TOOL_SETS",
    "build_tools",
    "default_registry",
]
