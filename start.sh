#!/bin/bash
# Jarvis starten
cd "$(dirname "$0")"

# Alte Instanz beenden
if [ -f /tmp/jarvis.pid ]; then
    OLD_PID=$(cat /tmp/jarvis.pid)
    kill -9 "$OLD_PID" 2>/dev/null
    rm -f /tmp/jarvis.pid
fi

# Kurz warten damit Telegram die Session freigibt
sleep 2

echo "🤖 Starte Jarvis..."
nohup /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -u main.py \
    > /tmp/jarvis_out.log 2>&1 &
echo $! > /tmp/jarvis_pid.txt

sleep 4
if kill -0 $(cat /tmp/jarvis_pid.txt) 2>/dev/null; then
    echo "✅ Jarvis läuft (PID $(cat /tmp/jarvis_pid.txt))"
    echo "📋 Log: tail -f /tmp/jarvis_out.log"
else
    echo "❌ Jarvis konnte nicht starten – Log:"
    cat /tmp/jarvis_out.log
fi
