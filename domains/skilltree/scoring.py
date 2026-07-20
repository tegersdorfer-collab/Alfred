"""Skilltree-Scoring — reine Funktionen, kein I/O.

Rechnet aus einer Signal-History (list[SignalEvent]) pro Achse XP + Level. Ältere
Signale zerfallen je nach Retention-Klasse ihrer Komponente (fast/slow/permanent),
sodass das Level den *aktuellen* Zustand spiegelt, nicht die Lebenssumme. Fehlt eine
Achse an Daten, ist sie ehrlich Level 0 — nie geraten.
"""
from __future__ import annotations

from datetime import date

# Halbwertszeit in Tagen je Retention-Klasse. permanent → kein Zerfall.
RETENTION_HALFLIFE: dict[str, float | None] = {
    "fast": 14.0,       # Kondition, Fokus-Streak, Momentum
    "slow": 90.0,       # Kraft-Basis, gefestigtes Wissen
    "permanent": None,  # tief verankert (verhält sich fast wie ein Node)
}


def retention_decay(retention: str, elapsed_days: float) -> float:
    """Multiplikativer Faktor 0..1 für ein Signal, das `elapsed_days` alt ist.

    permanent → 1.0. Sonst exponentiell: 0.5 ** (elapsed / halflife).
    """
    halflife = RETENTION_HALFLIFE.get(retention)
    if halflife is None:
        return 1.0
    if elapsed_days <= 0:
        return 1.0
    return round(0.5 ** (elapsed_days / halflife), 6)


def axis_xp(signals: list[dict], axis_cfg: dict, now: date) -> float:
    """Gewichtete, zeit-gedämpfte XP-Summe der Signale dieser Achse.

    Signale mit unbekanntem `kind` (nicht in der Achsen-Config) fallen raus.
    """
    comps = axis_cfg.get("components", {})
    total = 0.0
    for s in signals:
        comp = comps.get(s["kind"])
        if not comp:
            continue
        elapsed = (now - date.fromisoformat(s["ts"])).days
        factor = retention_decay(comp["retention"], elapsed)
        total += s["value"] * s.get("count", 1) * comp["weight"] * factor
    return round(total, 1)
