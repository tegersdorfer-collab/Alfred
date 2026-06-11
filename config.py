import os
from dotenv import load_dotenv

load_dotenv()

# LLM
OLLAMA_MODEL      = os.getenv("OLLAMA_MODEL", "qwen3:14b")         # Fallback wenn Routing aus
OLLAMA_FAST_MODEL = os.getenv("OLLAMA_FAST_MODEL", "llama3.2:3b")  # 3B-Klassifikator (≠ Agent-Routing)
OLLAMA_BASE_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")          # Modell warm halten

# ── Agent-Modell-Routing: schnell wenn möglich, stark wenn nötig ──────────────
# Einfache Anfragen/Tool-Aktionen → schnelles Modell; komplexe Analysen/Reflexion/
# Beratung → starkes Modell. Rein heuristisch (kein LLM-Call). Aus: LLM_ROUTING=false.
LLM_ROUTING        = os.getenv("LLM_ROUTING", "true").strip().lower() in ("1", "true", "yes", "on", "ja")
AGENT_MODEL_FAST   = os.getenv("AGENT_MODEL_FAST", "qwen3.5:4b")   # residentes Arbeitstier
AGENT_MODEL_STRONG = os.getenv("AGENT_MODEL_STRONG", "qwen3.5:9b") # nur bei komplexen Anfragen
# Starkes Modell schnell wieder entladen (16-GB-RAM: nicht beide dauerhaft warm halten)
OLLAMA_KEEP_ALIVE_STRONG = os.getenv("OLLAMA_KEEP_ALIVE_STRONG", "2m")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = "claude-haiku-4-5"  # Für schwere Tasks

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
# Absender-Allowlist – nur diese Telegram-IDs dürfen mit Jarvis reden.
# Kommagetrennt (User- oder Chat-IDs); TELEGRAM_CHAT_ID wird automatisch ergänzt.
TELEGRAM_ALLOWED_IDS = {
    s.strip()
    for s in (os.getenv("TELEGRAM_ALLOWED_IDS", "").split(",") + [TELEGRAM_CHAT_ID])
    if s.strip()
}

# Besitzer (persönliche Daten – aus .env, NICHT im Repo)
OWNER_NAME     = os.getenv("OWNER_NAME", "Timo")
OWNER_EMAIL    = os.getenv("OWNER_EMAIL", "")
OWNER_TIMEZONE = os.getenv("OWNER_TIMEZONE", "Europe/Berlin")

# Datenquellen (direkt von der Quelle – unabhängig von ai-dashboard)
HEALTH_JSON_PATH  = os.getenv(
    "HEALTH_JSON_PATH",
    "~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/Health.json",
)
CALENDAR_ICS_URLS = os.getenv("CALENDAR_ICS_URLS", "")   # kommagetrennt

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/jarvis")

# Thermal
THERMAL_TARGET_CELSIUS = float(os.getenv("THERMAL_TARGET_CELSIUS", "70.0"))
THERMAL_MAX_CELSIUS    = float(os.getenv("THERMAL_MAX_CELSIUS", "85.0"))

# Idle Loop
IDLE_MIN_SLEEP_S          = 2        # Minimum Pause zwischen Idle-Schritten
IDLE_MAX_SLEEP_S          = 60       # Maximum Pause (bei hoher Temp)
IDLE_EVAL_AFTER_S         = 600      # Nach 10 Min Task neu bewerten

# Proaktive Nachrichten
PROACTIVE_WAIT_AFTER_CONV = 10 * 60  # 10 Min nach Gespräch → Follow-up
PROACTIVE_INTERVAL        = 90 * 60  # 90 Min Mindestabstand danach

# Memory
LZG_EMBED_MODEL  = "nomic-embed-text"   # Lokales Embedding via Ollama
LZG_TOP_K        = 5                    # Wie viele Memories beim Start laden
KZG_MAX_TURNS    = 20                   # Max Turns im Kurzzeitgedächtnis

# Search
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

# Google Calendar (OAuth2 – für Jarvis → Google Termine schreiben)
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_CALENDAR_ID   = os.getenv("GOOGLE_CALENDAR_ID", "primary")  # 'primary' = Haupt-Kalender
