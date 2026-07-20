"""Signal-Collector — der einzige I/O-Punkt des Skilltree.

Zieht harte Signale aus bestehenden Mantis-Stores und normalisiert sie auf
SignalEvent. Kennt die Stores, aber keine Scoring-Logik. Erweiterung = eine neue
collect_from_*-Funktion + ein Aufruf in collect_signals (der Erweiterungspunkt).
"""
from __future__ import annotations

from datetime import date


def collect_from_health(health_rows: list) -> list[dict]:
    """Health-Rows → Körper-Signale.

    - Trainingsminuten > 0 → ein `training`-Signal (value = Minuten/30, gedeckelt bei 2).
    """
    out: list[dict] = []
    for h in health_rows:
        mins = getattr(h, "exercise_minutes", None) or 0
        if mins > 0:
            out.append({
                "axis": "koerper", "kind": "training",
                "value": round(min(mins / 30.0, 2.0), 2),
                "ts": str(h.date), "source": "health", "count": 1,
            })
    return out


def collect_signals(dashboard, now: date) -> list[dict]:
    """Alle harten Signale der letzten 90 Tage aus den vorhandenen Stores.

    M1: Health. Weitere Quellen (Second Brain, Habits, Git) docken hier an —
    je eine collect_from_*-Funktion, hier aufgerufen und in die Liste gemischt.
    """
    signals: list[dict] = []
    if dashboard is not None:
        signals += collect_from_health(dashboard.get_recent_health(days=90))
    return signals
