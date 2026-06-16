"""Automatisch von Alfred erstelltes Skill: Quadriert eine Zahl (multipliziert sie mit sich selbst)
Erstellt: 2026-06-16T21:28:58
"""
from core import tools as T


@T.register("square_number", "Quadriert eine Zahl", {"type": "object", "properties": {"number": {"type": "number", "description": "Die Zahl die quadriert werden soll"}}, "required": ["number"]}, ["number"], "math")
async def square_number(number) -> str:
    num = float(number)
    result = num * num
    return f"{num}² = {result}"
