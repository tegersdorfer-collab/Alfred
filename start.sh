#!/bin/bash
# Mantis starten
cd "$(dirname "$0")"

# Alte Instanz beenden
if [ -f /tmp/mantis.pid ]; then
    OLD_PID=$(cat /tmp/mantis.pid)
    kill -9 "$OLD_PID" 2>/dev/null
    rm -f /tmp/mantis.pid
fi

# Kurz warten damit Telegram die Session freigibt
sleep 2

PYTHON=$(which python3.14 2>/dev/null || which python3 2>/dev/null || which python 2>/dev/null)
if [ -z "$PYTHON" ]; then echo "❌ Kein Python gefunden"; exit 1; fi

echo "🤖 Starte Mantis..."
nohup "$PYTHON" -u main.py \
    > /tmp/mantis_out.log 2>&1 &
echo $! > /tmp/mantis_pid.txt

sleep 4
if kill -0 $(cat /tmp/mantis_pid.txt) 2>/dev/null; then
    echo "✅ Mantis läuft (PID $(cat /tmp/mantis_pid.txt))"
    echo "📋 Log: tail -f /tmp/mantis_out.log"
else
    echo "❌ Mantis konnte nicht starten – Log:"
    cat /tmp/mantis_out.log
fi
