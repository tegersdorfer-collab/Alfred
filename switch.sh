#!/bin/bash
# Modell wechseln und Alfred neu starten.
#
#   ./switch.sh            → zeigt aktuelles Modell + Routing-Status
#   ./switch.sh route on   → Auto-Routing AN (4B schnell ↔ 9B bei komplexen Anfragen)
#   ./switch.sh route off  → Routing AUS (nutzt einzelnes OLLAMA_MODEL unten)
#   ./switch.sh 4b         → qwen3.5:4b (3,4 GB – Tool-Calling-König, sehr schnell)
#   ./switch.sh 3.5 | 9b   → qwen3.5:9b (6,6 GB – mehr Reasoning, stärker als 14b)
#   ./switch.sh 8b         → qwen3:8b   (alt, ~5 GB)
#   ./switch.sh 14b        → qwen3:14b  (alt, ~9 GB – eng auf 16 GB)
#   ./switch.sh <tag>      → beliebiger Ollama-Tag (z.B. gemma4:e4b)
#
# Hinweis: Bei Routing AN wird OLLAMA_MODEL ignoriert – stattdessen AGENT_MODEL_FAST/
# _STRONG (Default 4b/9b). Der MLX-Runner ist separat (serverseitig OLLAMA_EXPERIMENT).
cd "$(dirname "$0")"

case "$1" in
  route)
    case "$2" in
      on|true)   VAL=true ;;
      off|false) VAL=false ;;
      *) echo "Nutzung: ./switch.sh route on|off"; exit 1 ;;
    esac
    if grep -qE '^LLM_ROUTING=' .env; then
      sed -i '' "s|^LLM_ROUTING=.*|LLM_ROUTING=$VAL|" .env
    else
      printf '\nLLM_ROUTING=%s\n' "$VAL" >> .env
    fi
    echo "✅ Routing → $VAL"
    echo "🔄 Starte Alfred neu ..."
    ./start.sh
    exit 0 ;;
  4b)     MODEL="qwen3.5:4b" ;;
  3.5|9b) MODEL="qwen3.5:9b" ;;
  8b)   MODEL="qwen3:8b" ;;
  14b)  MODEL="qwen3:14b" ;;
  "")
    ROUTE=$(grep -E '^LLM_ROUTING=' .env 2>/dev/null | cut -d= -f2)
    CUR=$(grep -E '^OLLAMA_MODEL=' .env 2>/dev/null | cut -d= -f2)
    if [ "${ROUTE:-true}" != "false" ]; then
      echo "Routing: AN  (schnell: qwen3.5:4b ↔ stark: qwen3.5:9b)"
    else
      echo "Routing: AUS (einzelnes Modell: ${CUR:-<Default qwen3:14b>})"
    fi
    echo "Verfügbar lokal:"
    ollama list 2>/dev/null | awk 'NR>1 {print "  - "$1}'
    echo "Nutzung: ./switch.sh [route on|off | 4b|3.5|8b|14b | <ollama-tag>]"
    exit 0 ;;
  *)    MODEL="$1" ;;
esac

# Sicherstellen, dass das Modell lokal vorhanden ist
if ! ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then
  echo "⚠️  $MODEL ist nicht lokal vorhanden."
  read -r -p "Jetzt mit 'ollama pull $MODEL' laden? [y/N] " ans
  [ "$ans" = "y" ] && ollama pull "$MODEL" || { echo "Abgebrochen."; exit 1; }
fi

# OLLAMA_MODEL in .env setzen (Zeile ersetzen oder anhängen)
if grep -qE '^OLLAMA_MODEL=' .env; then
  sed -i '' "s|^OLLAMA_MODEL=.*|OLLAMA_MODEL=$MODEL|" .env
else
  printf '\nOLLAMA_MODEL=%s\n' "$MODEL" >> .env
fi

echo "✅ Modell → $MODEL"
echo "🔄 Starte Alfred neu ..."
./start.sh
