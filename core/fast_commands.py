"""Deterministische Fast-Path-Befehle — kritische Fixbefehle ohne LLM.

Kleine Modelle (gemma4:e2b) rufen unter dem vollen System-Prompt bei Tool-Befehlen
manchmal gar kein Tool auf, sondern täuschen Erfolg vor ("Lampe an ✓", ohne zu
schalten). Für die wenigen kritischen Fixbefehle (Licht, Roboter-Not-Stopp) ist das
inakzeptabel. Diese Schicht erkennt sie regelbasiert und ruft das Tool DIREKT —
100% zuverlässig, sofort, modellunabhängig.

Designprinzip: **Fehlalarme (Konversation kapern) sind schlimmer als Auslassungen**
(dann übernimmt eben der Agent). Die Regeln sind daher bewusst eng: Fragezeichen →
niemals Fast-Path; Lampe braucht ein Kommando-Verb oder eine sehr kurze Äußerung.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class FastCommand:
    tool: str
    args: dict
    label: str  # fürs Logging


_LAMP = {"lampe", "licht", "schreibtischlampe"}
_ON = {"an", "ein", "anmachen", "einschalten", "anschalten"}
_OFF = {"aus", "ausmachen", "ausschalten", "abschalten"}
# Reihenfolge-relevant: Farbe/Helligkeit vor an/aus prüfen.
_COLORS = {"rot": "rot", "grün": "gruen", "gruen": "gruen", "blau": "blau",
           "weiß": "weiss", "weiss": "weiss", "warmweiß": "warmweiss", "warmweiss": "warmweiss"}
_BRIGHT = {"heller": "heller", "dunkler": "dunkler"}
_CMD_VERBS = {"mach", "macht", "mache", "schalt", "schalte", "schaltet",
              "dreh", "drehe", "stell", "stelle", "setz", "setze"}

_ROBOT = {"roboter", "robot", "droide", "droid", "x5"}
_STOP = {"stopp", "stop", "stoppen", "halt", "anhalten"}
_HARD_STOP = {"notaus", "notstopp", "nothalt", "notstop"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def match(text: str) -> FastCommand | None:
    """Gibt einen FastCommand zurück, wenn die Äußerung ein eindeutiger Fixbefehl
    ist — sonst None (dann übernimmt der Agent)."""
    if "?" in text:
        return None  # Fragen sind keine Befehle
    w = _words(text)
    if not w:
        return None

    # ── Roboter-Not-Stopp (Sicherheit) ───────────────────────────────────────
    if (w & _HARD_STOP) or (w & _ROBOT and w & _STOP):
        return FastCommand("robot_control", {"action": "stopp"}, "robot-stopp")

    # ── Lampe / Licht ─────────────────────────────────────────────────────────
    if w & _LAMP:
        # Nur echte Kommandos: entweder ein Kommando-Verb oder sehr kurz ("lampe an").
        if not (w & _CMD_VERBS or len(w) <= 3):
            return None
        for token, action in _COLORS.items():
            if token in w:
                return FastCommand("lampe", {"action": action}, f"lampe-{action}")
        for token, action in _BRIGHT.items():
            if token in w:
                return FastCommand("lampe", {"action": action}, f"lampe-{action}")
        if w & _OFF:
            return FastCommand("lampe", {"action": "aus"}, "lampe-aus")
        if w & _ON:
            return FastCommand("lampe", {"action": "an"}, "lampe-an")

    return None
