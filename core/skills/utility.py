"""
Utility-Tools — aus core/skills.py extrahiert (verhaltensgleich).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
"""
import logging
from datetime import date, datetime

from core import tools as T
from core.timeparse import parse_datetime, parse_date
from core.skill_context import CTX
from domains import habits, fitness, nutrition, journal, goals, weather, tasks as tasks_d

log = logging.getLogger("core.skills")


@T.register("calculate",
    "Führt eine mathematische Berechnung exakt aus. "
    "Nutze dies IMMER wenn du Zahlen addierst, subtrahierst, multiplizierst, dividierst "
    "oder Durchschnitte, Prozente, Verhältnisse berechnest — niemals im Kopf rechnen.",
    {"expression": {"type": "string", "description": "Mathematischer Ausdruck z.B. '111 / 36' oder '(80 + 90) / 2'"}},
    ["expression"], "utility")
async def _calculate(expression: str) -> str:
    import ast
    import math
    import operator
    import statistics

    _OPS = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv,
        ast.USub: operator.neg, ast.UAdd: operator.pos,
    }
    _NAMES = {k: v for k, v in vars(math).items() if not k.startswith("_")}
    _NAMES["statistics"] = statistics

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.Name) and node.id in _NAMES:
            return _NAMES[node.id]
        if isinstance(node, ast.Call):
            fn = _eval(node.func)
            if callable(fn):
                return fn(*[_eval(a) for a in node.args])
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "statistics":
            attr = getattr(statistics, node.attr, None)
            if callable(attr) and not node.attr.startswith("_"):
                return attr
        if isinstance(node, ast.List):
            return [_eval(e) for e in node.elts]
        raise ValueError(f"Nicht erlaubter Ausdruck: {ast.dump(node)}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree.body)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Fehler: {e}"
