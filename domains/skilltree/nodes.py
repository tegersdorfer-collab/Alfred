"""Meilenstein-Nodes — permanent, reine Logik.

Ein Node schaltet frei, sobald seine Bedingung *je* erfüllt war (max value eines
signal_kind ≥ threshold). Anders als das Achsen-Level zerfällt ein Node nie — das
"hab ich mal geschafft" bleibt stehen. Ableitung aus der Signal-History, kein State.
"""
from __future__ import annotations


def unlocked_nodes(signals: list[dict], node_defs: list[dict]) -> list[dict]:
    """Alle Nodes, deren Schwelle in der History je erreicht wurde."""
    out: list[dict] = []
    for nd in node_defs:
        vals = [s["value"] for s in signals if s["kind"] == nd["signal_kind"]]
        if vals and max(vals) >= nd["threshold"]:
            out.append({"key": nd["key"], "label": nd["label"], "axis": nd["axis"]})
    return out
