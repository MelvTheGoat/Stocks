"""Evaluates one arithmetic expression, then exits. Run as a subprocess.

Reads the expression from standard input and prints the result. Only arithmetic
is possible: the expression is parsed to a syntax tree and any node that is not a
number, an operator, a comparison or a call to one of a short list of maths
functions is refused. There is no way to reach a name, an attribute, a subscript,
an import or a function that was not whitelisted.

Running it in a separate process is belt and braces on top of that. The parser
already makes arbitrary code impossible; the process boundary means that even a
bug in the parser cannot touch the caller, and a timeout can be enforced from
outside by killing it.
"""

from __future__ import annotations

import ast
import math
import operator
import sys

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

_COMPARE = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "pow": pow,
}

_CONSTANTS = {"pi": math.pi, "e": math.e}

# An exponent big enough to hang the process is the one denial of service the
# parser cannot rule out by shape alone.
_MAX_EXPONENT = 1000


class Refused(Exception):
    pass


def _evaluate(node: ast.AST) -> object:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise Refused(f"only numbers are allowed, not {type(node.value).__name__}")
    if isinstance(node, ast.BinOp):
        handler = _BINARY.get(type(node.op))
        if handler is None:
            raise Refused(f"operator {type(node.op).__name__} is not allowed")
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(float(right)) > _MAX_EXPONENT:
            raise Refused(f"exponent above {_MAX_EXPONENT} is not allowed")
        return handler(left, right)
    if isinstance(node, ast.UnaryOp):
        handler = _UNARY.get(type(node.op))
        if handler is None:
            raise Refused(f"operator {type(node.op).__name__} is not allowed")
        return handler(_evaluate(node.operand))
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1:
            raise Refused("chained comparisons are not allowed")
        handler = _COMPARE.get(type(node.ops[0]))
        if handler is None:
            raise Refused("that comparison is not allowed")
        return handler(_evaluate(node.left), _evaluate(node.comparators[0]))
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_evaluate(element) for element in node.elts]
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise Refused(f"the name {node.id!r} is not available; only numbers and maths functions")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise Refused("only plain function calls are allowed")
        function = _FUNCTIONS.get(node.func.id)
        if function is None:
            raise Refused(
                f"{node.func.id!r} is not available. Allowed: {', '.join(sorted(_FUNCTIONS))}"
            )
        if node.keywords:
            raise Refused("keyword arguments are not allowed")
        return function(*[_evaluate(argument) for argument in node.args])
    raise Refused(f"{type(node).__name__} is not allowed in an expression")


def evaluate(expression: str) -> object:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise Refused(f"could not parse the expression: {error.msg}") from error
    return _evaluate(tree)


def main() -> int:
    expression = sys.stdin.read()
    try:
        print(repr(evaluate(expression)))
    except Refused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    except (ArithmeticError, ValueError, TypeError) as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
