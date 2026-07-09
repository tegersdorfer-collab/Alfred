"""macOS-Bluetooth-Entitlement-Check für den Roboter-BLE-Zugriff.

Hintergrund: Der python.org-Framework-Interpreter braucht in seiner
`Python.app/Contents/Info.plist` den Schlüssel `NSBluetoothAlwaysUsageDescription`.
Fehlt er, killt macOS beim ERSTEN BLE-Zugriff den GANZEN Prozess hart
(SIGABRT/TCC) — ohne Erlauben-Dialog. Der Patch geht bei jedem Python-Update
verloren.

Dieses Modul erkennt den Zustand VOR dem BLE-Zugriff, damit der Roboter-Manager
mit einer klaren Fehlermeldung ablehnen kann, statt Mantis komplett abstürzen zu
lassen. Fix: `scripts/fix_bluetooth.sh`.
"""
from __future__ import annotations

import os
import plistlib
import sys

_KEY = "NSBluetoothAlwaysUsageDescription"

_HINT = (
    "Bluetooth-Berechtigung fehlt im Python-Interpreter — ein BLE-Zugriff würde "
    "Mantis komplett abstürzen lassen (SIGABRT/TCC). Fix: einmalig "
    "`scripts/fix_bluetooth.sh` ausführen, dann Mantis neu starten. "
    "Tritt typischerweise nach einem Python-Update auf."
)


def info_plist_path() -> str | None:
    """Pfad zur Info.plist des laufenden Framework-Interpreters (nur macOS)."""
    if sys.platform != "darwin":
        return None
    cand = os.path.join(sys.prefix, "Resources", "Python.app", "Contents", "Info.plist")
    return cand if os.path.exists(cand) else None


def bluetooth_entitlement_ok(plist_path: str | None = "__auto__") -> bool:
    """True, wenn BLE gefahrlos genutzt werden kann.

    - Nicht-macOS: immer True (kein solches Entitlement nötig).
    - Plist nicht auffindbar/lesbar: True (nicht fälschlich blockieren).
    - macOS mit Plist: True nur, wenn der Bluetooth-Schlüssel vorhanden ist.
    """
    if sys.platform != "darwin":
        return True
    path = info_plist_path() if plist_path == "__auto__" else plist_path
    if not path or not os.path.exists(path):
        return True
    try:
        with open(path, "rb") as f:
            return _KEY in plistlib.load(f)
    except Exception:
        return True


def entitlement_hint() -> str:
    return _HINT
