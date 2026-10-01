"""Arithmetic, run in a separate process with a timeout.

Language models are unreliable at multi-step arithmetic and entirely reliable at
writing down the sum they want computed. Giving them a calculator converts a
class of silent wrong answers into a class of correct ones, and Experiment B
measures how much that is worth.

The evaluation happens in `calc_worker`, as a subprocess, for three reasons: a
bug in the expression parser cannot reach this process, a runaway computation can
be killed from outside, and the subprocess is started with no network reachable
by anything it could call anyway.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from stockagent.tools.base import ToolResult, ToolSpec, require

DEFAULT_TIMEOUT_S = 5.0


@dataclass
class CalculatorTool:
    timeout_s: float = DEFAULT_TIMEOUT_S
    # Overridable so a test can prove the timeout actually fires.
    python: str = sys.executable

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="calculate",
            description=(
                "Work out one arithmetic expression exactly. Use this for every "
                "calculation rather than doing it in your head: percentage changes, "
                "ratios, totals. Example: '(118.0 / 100.0 - 1) * 100'. "
                "Available functions: abs, round, min, max, sum, sqrt, log, log10, exp, "
                "floor, ceil, pow. Only arithmetic is possible; there are no variables."
            ),
            parameters={
                "expression": {
                    "type": "string",
                    "description": "an arithmetic expression, for example '(118/100 - 1) * 100'",
                }
            },
            required=("expression",),
        )

    def run(self, **arguments) -> ToolResult:
        (expression,) = require(arguments, "expression")
        expression = str(expression)

        try:
            completed = subprocess.run(
                [self.python, "-I", "-m", "stockagent.tools.calc_worker"],
                input=expression,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult.failure(
                f"the calculation did not finish within {self.timeout_s:g} seconds; "
                "simplify the expression"
            )
        except OSError as error:
            return ToolResult.failure(f"the calculator could not be started: {error}")

        if completed.returncode != 0:
            detail = (completed.stderr or "").strip() or "the calculation failed"
            return ToolResult.failure(detail.splitlines()[0])

        value = (completed.stdout or "").strip()
        if not value:
            return ToolResult.failure("the calculation produced no result")
        return ToolResult.success(f"{expression} = {value}", sources=(), value=value)
