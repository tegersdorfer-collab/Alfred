#!/bin/bash
# Fügt NSBluetoothAlwaysUsageDescription in die Info.plist des laufenden Python-
# Framework-Interpreters ein und signiert Python.app ad-hoc neu — damit Mantis
# per Bluetooth den X5-Roboter steuern kann, ohne beim ersten BLE-Zugriff hart
# abzustürzen (SIGABRT/TCC).
#
# Idempotent: ist der Schlüssel schon da, passiert nichts.
# Nach einem Python-Update erneut ausführen. Ggf. mit sudo (Schreibrechte auf
# /Library/Frameworks). Danach Mantis neu starten.
set -euo pipefail

PY="$(command -v python3.14 || command -v python3)"
PLIST="$("$PY" -c 'import os,sys; print(os.path.join(sys.prefix,"Resources","Python.app","Contents","Info.plist"))')"
APP="$(dirname "$(dirname "$PLIST")")"          # .../Python.app
KEY="NSBluetoothAlwaysUsageDescription"
DESC="Mantis nutzt Bluetooth zur Steuerung des X5-Roboters (EVRobot2)."
BACKUP="$(cd "$(dirname "$0")/.." && pwd)/data/python-Info.plist.pre-bluetooth.bak"

if [ ! -f "$PLIST" ]; then
  echo "❌ Info.plist nicht gefunden: $PLIST"
  echo "   (Kein python.org-Framework-Interpreter? Dann ist der Patch evtl. gar nicht nötig.)"
  exit 1
fi

if /usr/libexec/PlistBuddy -c "Print :$KEY" "$PLIST" >/dev/null 2>&1; then
  echo "✅ Bluetooth-Berechtigung bereits vorhanden — nichts zu tun."
  exit 0
fi

if [ ! -w "$PLIST" ]; then
  echo "⚠️  Keine Schreibrechte auf $PLIST"
  echo "   Bitte erneut mit sudo ausführen:  sudo $0"
  exit 2
fi

echo "→ Sichere Original nach $BACKUP"
cp "$PLIST" "$BACKUP"

echo "→ Setze $KEY"
/usr/libexec/PlistBuddy -c "Add :$KEY string '$DESC'" "$PLIST"

echo "→ Signiere Python.app ad-hoc neu"
codesign --force --sign - --preserve-metadata=entitlements,flags "$APP"

echo "✅ Fertig. Bitte Mantis neu starten (./start.sh)."
