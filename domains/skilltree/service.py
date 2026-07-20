"""Skilltree-Service-Facade — verbindet Collector + reine Logik zum Gesamt-State.

Der eine Einstieg für Router/Voice/Widget. Stateless: alles aus der Signal-History
abgeleitet (wie health_scores). `quest_since` grenzt das Quest-Fenster ab (z.B.
Wochenstart) — kommt vom Aufrufer, damit die Facade zeitfrei/testbar bleibt.
"""
from __future__ import annotations

from datetime import date

from domains.skilltree.config import AXES, NODE_DEFS, QUEST_POOL
from domains.skilltree.nodes import unlocked_nodes
from domains.skilltree.quests import pick_quests, quest_progress
from domains.skilltree.scoring import axis_level
from domains.skilltree.signals import collect_signals


def build_skilltree_state(dashboard, now: date, quest_since: str) -> dict:
    signals = collect_signals(dashboard, now)
    axes = [axis_level(signals, cfg, now) for cfg in AXES]
    nodes = unlocked_nodes(signals, NODE_DEFS)
    quests = []
    for q in pick_quests(axes, QUEST_POOL):
        active = {**q, "since": quest_since}
        quests.append({**active, "progress": quest_progress(active, signals, now)})
    return {"axes": axes, "nodes": nodes, "quests": quests}
