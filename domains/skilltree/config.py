"""Skilltree-Konfiguration — Daten, kein Code.

Fünf Start-Achsen (erweiterbar: neue Achse = ein Eintrag hier, kein Umbau). Jede
Achse mappt Signal-`kind`s auf Gewicht + Retention-Klasse. NODE_DEFS = permanente
Meilensteine, QUEST_POOL = Vorlagen für die Quest-Engine.
"""
from __future__ import annotations

AXES: list[dict] = [
    {"key": "koerper", "label": "Körper", "components": {
        "training": {"weight": 12.0, "retention": "fast"},
        "kondition": {"weight": 8.0, "retention": "fast"},
        "kraft": {"weight": 15.0, "retention": "slow"},
    }},
    {"key": "wissen", "label": "Wissen", "components": {
        "zettel": {"weight": 8.0, "retention": "slow"},
        "lernpfad": {"weight": 12.0, "retention": "slow"},
        "studium": {"weight": 15.0, "retention": "permanent"},
    }},
    {"key": "schaffen", "label": "Schaffen", "components": {
        "commit": {"weight": 6.0, "retention": "fast"},
        "projekt": {"weight": 20.0, "retention": "permanent"},
    }},
    {"key": "geist", "label": "Geist", "components": {
        "reflexion": {"weight": 8.0, "retention": "fast"},
        "insight": {"weight": 10.0, "retention": "slow"},
    }},
    {"key": "disziplin", "label": "Disziplin", "components": {
        "streak": {"weight": 10.0, "retention": "fast"},
        "habit": {"weight": 8.0, "retention": "fast"},
    }},
]

NODE_DEFS: list[dict] = [
    {"key": "dl_100", "label": "100 kg Kreuzheben", "axis": "koerper", "signal_kind": "kraft", "threshold": 100.0},
    {"key": "notes_100", "label": "100 Zettel angelegt", "axis": "wissen", "signal_kind": "zettel_total", "threshold": 100.0},
    {"key": "ship_first", "label": "Erstes Projekt released", "axis": "schaffen", "signal_kind": "projekt", "threshold": 1.0},
]

QUEST_POOL: list[dict] = [
    {"key": "train_3x", "axis": "koerper", "label": "3× trainieren diese Woche", "target_kind": "training", "target_count": 3},
    {"key": "zettel_5", "axis": "wissen", "label": "5 neue Zettel schreiben", "target_kind": "zettel", "target_count": 5},
    {"key": "commit_5", "axis": "schaffen", "label": "An 5 Tagen committen", "target_kind": "commit", "target_count": 5},
    {"key": "reflect_3", "axis": "geist", "label": "3× reflektieren/journaln", "target_kind": "reflexion", "target_count": 3},
    {"key": "streak_5", "axis": "disziplin", "label": "5-Tage-Habit-Streak halten", "target_kind": "streak", "target_count": 5},
]


def axis_by_key(key: str) -> dict | None:
    return next((a for a in AXES if a["key"] == key), None)
