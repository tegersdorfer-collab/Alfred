"""Rote Linien der UI-Automatik — destruktive/riskante Aktionen hart erkennen.

Sicherheitsprinzip: Die Erkennung passiert in dieser Primitivschicht, BEVOR
geklickt/getippt wird — nicht dem (kleinen) Modell überlassen. Selbst wenn der
Agent „klick Löschen" entscheidet, blockt der Aufrufer hier.

Matching per Token (ganze Wörter), NICHT per Teilstring: sonst würde
„Absenderadresse" fälschlich als „senden" gelten. Deckt sich mit Mantis'
Grundregeln (keine Passwörter eingeben, keine irreversiblen Aktionen ohne
ausdrückliche Freigabe).
"""
from __future__ import annotations

import re

# Ganze-Wort-Tokens (lowercase). Deutsch + Englisch.
REDLINE_KEYWORDS: frozenset[str] = frozenset({
    # Löschen / Entfernen
    "löschen", "delete", "entfernen", "remove", "papierkorb", "trash",
    # Senden
    "senden", "send", "abschicken",
    # Kaufen / Bezahlen / Überweisen
    "kaufen", "buy", "purchase", "bezahlen", "pay", "kasse", "checkout",
    "überweisen", "überweisung",
    # Veröffentlichen / Posten
    "veröffentlichen", "publish", "posten", "post", "tweet",
})

_SECURE_ROLE = "AXSecureTextField"


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", (text or "").lower()))


def is_secure_field(element: dict) -> bool:
    """True wenn das Element ein Passwort-/Sicherheitsfeld ist."""
    return element.get("role") == _SECURE_ROLE


def is_redline(element: dict) -> tuple[bool, str]:
    """Prüft, ob eine Aktion auf diesem Element eine rote Linie überschreitet.

    Rückgabe (True, Grund) wenn: Titel enthält ein Redline-Token (ganzes Wort)
    ODER das Element ist ein Sicherheits-/Passwortfeld. Sonst (False, "").
    """
    if is_secure_field(element):
        return True, "Passwort-/Sicherheitsfeld"
    hits = _tokens(element.get("title", "")) & REDLINE_KEYWORDS
    if hits:
        return True, f"destruktiv/riskant: ‚{sorted(hits)[0]}'"
    return False, ""
