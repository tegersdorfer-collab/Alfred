"""Quest-Engine — adaptive Auswahl + Auto-Completion, reine Logik.

Adaptiv: rostende Achsen (negativer Trend) werden zuerst gepusht (rundes Wachstum),
dann wird Momentum (positiver Trend) verstärkt. Completion wird aus harten Signalen
abgeleitet — keine manuelle Abhaken nötig, wo Daten fließen.
"""
from __future__ import annotations

from datetime import date


def classify_axes(axis_states: list[dict], rust_threshold: float = -5.0,
                  momentum_threshold: float = 5.0) -> dict:
    """Achsen nach Trend einteilen. rustend = trend ≤ rust_threshold,
    Momentum = trend ≥ momentum_threshold. Rest bleibt neutral."""
    rusting = [s["axis"] for s in axis_states if s["trend"] <= rust_threshold]
    momentum = [s["axis"] for s in axis_states if s["trend"] >= momentum_threshold]
    return {"rusting": rusting, "momentum": momentum}


def pick_quests(axis_states: list[dict], quest_pool: list[dict], n: int = 3) -> list[dict]:
    """Bis zu n Quests: erst für rostende Achsen (Priorität), dann Momentum, dann Rest.

    Reihenfolge der Achsen innerhalb einer Gruppe = schwächster Trend zuerst
    (rostend) bzw. stärkster zuerst (Momentum).
    """
    c = classify_axes(axis_states)
    trend = {s["axis"]: s["trend"] for s in axis_states}
    rusting = sorted(c["rusting"], key=lambda a: trend[a])            # negativster zuerst
    momentum = sorted(c["momentum"], key=lambda a: -trend[a])         # stärkster zuerst
    rest = [s["axis"] for s in axis_states if s["axis"] not in rusting and s["axis"] not in momentum]
    order = rusting + momentum + rest
    picked: list[dict] = []
    for axis in order:
        q = next((q for q in quest_pool if q["axis"] == axis), None)
        if q:
            picked.append(q)
        if len(picked) >= n:
            break
    return picked


def quest_progress(quest: dict, signals: list[dict], now: date) -> dict:
    """Fortschritt aus harten Signalen seit quest['since'] (inklusive).

    Filtert Signale nach kind und axis, zählt matched signals auf.
    """
    matched = [s for s in signals
               if s["kind"] == quest["target_kind"]
               and s["axis"] == quest["axis"]
               and s["ts"] >= quest["since"]]
    count = sum(s.get("count", 1) for s in matched)
    pct = min(1.0, count / quest["target_count"]) if quest["target_count"] else 0.0
    return {"count": count, "pct": round(pct, 2), "done": count >= quest["target_count"]}
