"""Skilltree-Scoring — reine Funktionen, kein I/O.

Rechnet aus einer Signal-History (list[SignalEvent]) pro Achse XP + Level. Ältere
Signale zerfallen je nach Retention-Klasse ihrer Komponente (fast/slow/permanent),
sodass das Level den *aktuellen* Zustand spiegelt, nicht die Lebenssumme. Fehlt eine
Achse an Daten, ist sie ehrlich Level 0 — nie geraten.
"""
from __future__ import annotations

from datetime import date, timedelta

# Halbwertszeit in Tagen je Retention-Klasse. permanent → kein Zerfall.
RETENTION_HALFLIFE: dict[str, float | None] = {
    "fast": 14.0,       # Kondition, Fokus-Streak, Momentum
    "slow": 90.0,       # Kraft-Basis, gefestigtes Wissen
    "permanent": None,  # tief verankert (verhält sich fast wie ein Node)
}


def retention_decay(retention: str, elapsed_days: float) -> float:
    """Multiplikativer Faktor 0..1 für ein Signal, das `elapsed_days` alt ist.

    permanent → 1.0 (kein Zerfall). fast/slow → exponentiell 0.5 ** (elapsed / halflife).
    Unbekannte Retention-Klasse → ValueError (Fehlkonfiguration nicht still schlucken).
    """
    if retention == "permanent":
        return 1.0
    halflife = RETENTION_HALFLIFE.get(retention)
    if halflife is None:
        raise ValueError(f"Unbekannte Retention-Klasse: {retention!r}")
    if elapsed_days <= 0:
        return 1.0
    return round(0.5 ** (elapsed_days / halflife), 6)


def axis_xp(signals: list[dict], axis_cfg: dict, now: date) -> float:
    """Gewichtete, zeit-gedämpfte XP-Summe der Signale DIESER Achse.

    Signale anderer Achsen (`axis` != axis_cfg["key"]) und Signale mit unbekanntem
    `kind` (nicht in der Achsen-Config) fallen raus.
    """
    comps = axis_cfg.get("components", {})
    key = axis_cfg["key"]
    total = 0.0
    for s in signals:
        if s["axis"] != key:
            continue
        comp = comps.get(s["kind"])
        if not comp:
            continue
        elapsed = (now - date.fromisoformat(s["ts"])).days
        factor = retention_decay(comp["retention"], elapsed)
        total += s["value"] * s.get("count", 1) * comp["weight"] * factor
    return round(total, 1)


def xp_to_level(xp: float, curve_k: float = 100.0) -> int:
    """Monoton, abflachend: Level = floor(sqrt(xp / curve_k)). 0 XP → Level 0."""
    if xp <= 0:
        return 0
    return int((xp / curve_k) ** 0.5)


def axis_level(signals: list[dict], axis_cfg: dict, now: date, curve_k: float = 100.0) -> dict:
    """XP + Level + 7-Tage-Trend für eine Achse (→ axis_state).

    Trend = XP(jetzt) − XP(vor 7 Tagen), auf denselben Signalen mit verschobenem
    `now` gerechnet (ältere Signale zählen dann stärker gedämpft / gar nicht).
    """
    xp_now = axis_xp(signals, axis_cfg, now)
    xp_prev = axis_xp([s for s in signals if s["ts"] <= (now - timedelta(days=7)).isoformat()],
                      axis_cfg, now - timedelta(days=7))
    return {
        "axis": axis_cfg["key"],
        "label": axis_cfg["label"],
        "xp": xp_now,
        "level": xp_to_level(xp_now, curve_k),
        "trend": round(xp_now - xp_prev, 1),
    }
