"""``*PARAMETER`` definitions, ``&name`` references and a whitelisted expression evaluator."""
from __future__ import annotations

import ast
import math
import operator
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .fields import FieldError, FieldSlot, parse_number
from .text import body, is_blank

TYPES = {"R": "real", "I": "integer", "C": "character"}
REFERENCE = re.compile(r"^\s*(-?)&([A-Za-z_][A-Za-z0-9_]*)\s*$")
_FORTRAN_D = re.compile(r"(?<=[0-9.])[dD](?=[+-]?\d)")


def _nint(x: float) -> float:
    return float(math.floor(abs(x) + 0.5) * (1 if x >= 0 else -1))


def _sign(a: float, b: float) -> float:
    return abs(a) if b >= 0 else -abs(a)


FUNCTIONS: dict[str, Callable[..., float]] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos,
    "atan": math.atan, "atan2": math.atan2, "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "sqrt": math.sqrt, "exp": math.exp, "log": math.log, "log10": math.log10, "abs": abs,
    "min": min, "max": max, "mod": math.fmod, "int": lambda x: float(math.trunc(x)),
    "aint": lambda x: float(math.trunc(x)), "nint": _nint, "sign": _sign,
}
_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


@dataclass
class ParameterDef:
    """One parameter definition as written in the deck (before evaluation)."""

    name: str
    type: str
    raw: str
    expression: bool
    local: bool
    data_line: int
    value_slot: FieldSlot | None = None
    value: float | int | str | None = None
    error: str | None = None

    @property
    def key(self) -> str:
        return self.name.lower()


def evaluate(expression: str, lookup: Mapping[str, float]) -> float:
    """Evaluate an LS-DYNA style arithmetic expression; names are case-insensitive."""
    # Names may be written bare (thick*2) or as references (&thick*2) inside expressions.
    source = _FORTRAN_D.sub("e", expression.strip()).replace("^", "**").replace("&", "")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as error:
        raise FieldError(f"Invalid expression {expression!r}") from error
    names = {k.lower(): v for k, v in lookup.items()}

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            return _BINARY[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](walk(node.operand))
        if isinstance(node, ast.Name):
            key = node.id.lower()
            if key not in names:
                raise FieldError(f"Undefined parameter {node.id!r} in {expression!r}")
            value = names[key]
            if isinstance(value, str):
                raise FieldError(f"Character parameter {node.id!r} used in arithmetic")
            return float(value)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords
                and node.func.id.lower() in FUNCTIONS):
            return float(FUNCTIONS[node.func.id.lower()](*(walk(a) for a in node.args)))
        raise FieldError(f"Unsupported construct in expression {expression!r}")

    try:
        return walk(tree)
    except (ArithmeticError, ValueError, TypeError) as error:
        if isinstance(error, FieldError):
            raise
        raise FieldError(f"Cannot evaluate {expression!r}: {error}") from error


def _split_name(prmr: str) -> tuple[str, str] | None:
    text = prmr.strip()
    if not text:
        return None
    kind = text[0].upper()
    name = text[1:].strip()
    if kind not in TYPES or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise FieldError(f"Invalid parameter name field {prmr!r}")
    return TYPES[kind], name


def parse_definitions(keyword: str, data: list[tuple[int, str]]) -> tuple[list[ParameterDef], list[str]]:
    """Parse the data lines of a ``*PARAMETER`` or ``*PARAMETER_EXPRESSION`` block.

    ``data`` holds ``(data_line_index, line)`` pairs. Returns the definitions and a list
    of problems (malformed name fields are reported, not raised). Other ``*PARAMETER_*``
    keywords (``_DUPLICATION``, ``_TYPE``) carry settings, not definitions.
    """
    problems: list[str] = []
    local = "_LOCAL" in keyword
    expression = keyword.startswith("*PARAMETER_EXPRESSION")
    plain = keyword in ("*PARAMETER", "*PARAMETER_LOCAL", "*PARAMETER_MUTABLE", "*PARAMETER_LOCAL_MUTABLE")
    if not expression and not plain:
        return [], problems
    result: list[ParameterDef] = []
    for index, line in data:
        if is_blank(line):
            continue
        text = body(line)
        if expression:
            if "," in text:
                prmr, raw = text.split(",", 1)
                pairs = [(prmr, raw, FieldSlot(index, 0, 70, 1))]
            else:
                pairs = [(text[:10], text[10:], FieldSlot(index, 10, 70))]
        elif "," in text:
            tokens = [t.strip() for t in text.split(",")]
            pairs = [(tokens[k], tokens[k + 1], FieldSlot(index, 0, 10, k + 1)) for k in range(0, len(tokens) - 1, 2)]
        else:
            pairs = [(text[i:i + 10], text[i + 10:i + 20], FieldSlot(index, i + 10, 10)) for i in range(0, 80, 20)]
        for prmr, raw, slot in pairs:
            try:
                split = _split_name(prmr)
            except FieldError as error:
                problems.append(f"data line {index}: {error}")
                continue
            if split is None:
                continue
            kind, name = split
            result.append(ParameterDef(name=name, type=kind, raw=raw.strip(), expression=expression,
                                       local=local, data_line=index, value_slot=slot))
    return result, problems


def evaluate_definition(definition: ParameterDef, lookup: Mapping[str, float | int | str]) -> None:
    """Fill ``definition.value`` (or ``error``) using parameters visible at its position."""
    try:
        if definition.type == "character":
            definition.value = definition.raw
            return
        if definition.expression:
            number: float | int | None = evaluate(definition.raw, lookup)  # type: ignore[arg-type]
        else:
            number = parse_number(definition.raw)
            if number is None:
                raise FieldError(f"Parameter {definition.name!r} has no value")
        if definition.type == "integer":
            if float(number) != math.trunc(float(number)):
                raise FieldError(f"Integer parameter {definition.name!r} evaluates to {number}")
            number = int(number)
        else:
            number = float(number)
        definition.value = number
        definition.error = None
    except FieldError as error:
        definition.value, definition.error = None, str(error)


def reference(text: str) -> tuple[bool, str] | None:
    """Return ``(negated, name)`` if a field holds ``&name`` or ``-&name``."""
    match = REFERENCE.match(text)
    return (match.group(1) == "-", match.group(2)) if match else None
