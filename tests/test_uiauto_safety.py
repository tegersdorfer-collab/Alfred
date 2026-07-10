"""Tests für die roten Linien der UI-Automatik (tools/uiauto/safety.py).

Kern des Sicherheitsmodells: destruktive/riskante Elemente werden hart erkannt,
BEVOR geklickt wird — dem Modell wird das nicht anvertraut. Fokus daher auf
korrekter Trefferlage UND auf Nicht-Fehlalarmen (Teilwort-Fallen).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.uiauto.safety import is_redline, is_secure_field


def el(role="AXButton", title="", value=""):
    return {"ref": 0, "role": role, "title": title, "value": value, "enabled": True}


# ── Positive: destruktive/riskante Buttons ────────────────────────────────────

def test_delete_variants_are_redline():
    for t in ["Löschen", "löschen", "Delete", "Entfernen", "Remove", "In den Papierkorb", "Move to Trash"]:
        hit, _ = is_redline(el(title=t))
        assert hit, f"{t!r} sollte rote Linie sein"


def test_send_variants_are_redline():
    for t in ["Senden", "Send", "Abschicken", "Jetzt senden"]:
        assert is_redline(el(title=t))[0], t


def test_purchase_variants_are_redline():
    for t in ["Kaufen", "Buy now", "Purchase", "Bezahlen", "Zur Kasse", "Checkout", "Überweisen"]:
        assert is_redline(el(title=t))[0], t


def test_publish_variants_are_redline():
    for t in ["Veröffentlichen", "Publish", "Posten", "Post", "Tweet"]:
        assert is_redline(el(title=t))[0], t


def test_reason_is_returned():
    hit, reason = is_redline(el(title="Löschen"))
    assert hit and reason and "löschen" in reason.lower()


# ── Positive: Passwort-/Sicherheitsfelder ─────────────────────────────────────

def test_secure_text_field_is_redline():
    hit, reason = is_redline(el(role="AXSecureTextField", title="Passwort"))
    assert hit and "sicher" in reason.lower() or "passwort" in reason.lower()


def test_is_secure_field_helper():
    assert is_secure_field(el(role="AXSecureTextField"))
    assert not is_secure_field(el(role="AXTextField"))


# ── Negativ: harmlose Elemente / Teilwort-Fallen ──────────────────────────────

def test_harmless_buttons_not_redline():
    for t in ["OK", "Abbrechen", "Weiter", "Zurück", "Neue Notiz", "Suchen", "Play", "Speichern"]:
        assert not is_redline(el(title=t))[0], f"{t!r} darf KEINE rote Linie sein"


def test_substring_traps_not_redline():
    # Wörter, die ein Redline-Token als Teilstring enthalten, aber harmlos sind
    for t in ["Absenderadresse", "Sendungsverfolgung", "Postfach", "Postausgang anzeigen",
              "Verkaufszahlen", "Deletion-Verlauf öffnen"]:
        assert not is_redline(el(title=t))[0], f"{t!r} ist Teilwort-Falle, kein Redline"


def test_empty_title_not_redline():
    assert not is_redline(el(title=""))[0]


def test_normal_text_field_not_redline():
    assert not is_redline(el(role="AXTextField", title="Suche"))[0]
