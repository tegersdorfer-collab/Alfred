#!/bin/bash
# Alfred starten
cd "$(dirname "$0")"

# Alte Instanz beenden
if [ -f /tmp/alfred.pid ]; then
    OLD_PID=$(cat /tmp/alfred.pid)
    kill -9 "$OLD_PID" 2>/dev/null
    rm -f /tmp/alfred.pid
fi

# Kurz warten damit Telegram die Session freigibt
sleep 2

echo "🤖 Starte Alfred..."
nohup /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -u main.py \
    > /tmp/alfred_out.log 2>&1 &
echo $! > /tmp/alfred_pid.txt

sleep 4
if kill -0 $(cat /tmp/alfred_pid.txt) 2>/dev/null; then
    echo "✅ Alfred läuft (PID $(cat /tmp/alfred_pid.txt))"
    echo "📋 Log: tail -f /tmp/alfred_out.log"
else
    echo "❌ Alfred konnte nicht starten – Log:"
    cat /tmp/alfred_out.log
fi
