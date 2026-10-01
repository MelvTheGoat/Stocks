"""The agent loop, its prompt, and the trace it leaves behind."""

from stockagent.agent.loop import Agent, AgentOutcome
from stockagent.agent.protocol import ToolCall, parse_tool_call
from stockagent.agent.trace import Trace, TraceStep

__all__ = ["Agent", "AgentOutcome", "ToolCall", "Trace", "TraceStep", "parse_tool_call"]
