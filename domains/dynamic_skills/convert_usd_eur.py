"""Automatisch von Alfred erstelltes Skill: USD nach EUR umrechnen
Erstellt: 2026-06-16T19:53:37
"""
from core import tools as T


@T.register("convert_usd_eur", "Rechnet USD in EUR um (fester Demo-Kurs).", {"amount": {"type": "number", "description": "Betrag in USD"}}, ["amount"], "utility")
async def convert_usd_eur(amount: float) -> str:
    rate = 0.92
    return f"{amount} USD = {amount*rate:.2f} EUR"
