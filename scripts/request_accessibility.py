#!/usr/bin/env python3
"""Löst den macOS-Bedienungshilfen-Prompt aus.

Zweck: Das Freigeben einer nackten Binary über das '+' in den Systemeinstellungen
klappt oft nicht. Dieser Aufruf lässt macOS den richtigen Eintrag (Mantis' python3.14
bzw. das startende Terminal) AUTOMATISCH in die Bedienungshilfen-Liste eintragen —
du musst dann dort nur noch den Schalter aktivieren.

Ausführen (im selben Terminal, aus dem du ./start.sh startest):
  cd ~/Mantis && python3 scripts/request_accessibility.py

Dann: Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen → den neuen
Eintrag AKTIVIEREN → Mantis neu starten (./start.sh).
"""
import sys

try:
    from ApplicationServices import (
        AXIsProcessTrustedWithOptions,
        kAXTrustedCheckOptionPrompt,
    )
except Exception as e:
    print(f"❌ pyobjc/ApplicationServices nicht verfügbar: {e}")
    print("   pip install pyobjc-framework-ApplicationServices")
    sys.exit(1)

trusted = AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})

if trusted:
    print("✅ Dieser Prozess hat bereits Bedienungshilfen-Rechte.")
    print("   Falls Mantis trotzdem meckert: Mantis aus DIESEM Terminal neu starten (./start.sh).")
else:
    print("🔔 Der Bedienungshilfen-Dialog wurde ausgelöst und ein Eintrag zur Liste hinzugefügt.")
    print("   → Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen:")
    print("     den neuen Eintrag AKTIVIEREN, dann Mantis neu starten (./start.sh).")
