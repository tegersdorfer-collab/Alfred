import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Dashboard-Zugriff: kein App-Token mehr nötig (war PWA-feindlich, da iOS den
# Homescreen-Start_url fix auf "/" setzt, kein Platz für ?token=). Stattdessen
# bindet main.py den Server NUR auf die Tailscale-IP – im normalen LAN/WLAN ist
# das Dashboard dadurch unsichtbar, nur über Tailscale (eigene Geräte) erreichbar.
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "100.107.172.123")

# LLM – alles lokale läuft über Ollama (ein Prozess, kein llama-server mehr nötig).
OLLAMA_MODEL       = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")        # lokales Haupt-/Fallback-Modell
OLLAMA_BASE_URL     = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_KEEP_ALIVE   = os.getenv("OLLAMA_KEEP_ALIVE", "0")            # sofort entladen (lokales Modell springt nur sporadisch für Background-Tasks an)
AGENT_MODEL_FAST    = os.getenv("AGENT_MODEL_FAST", "qwen3.5:9b")    # Fast-Calls (gleiches Modell, kein extra RAM)
AGENT_MODEL_STRONG  = os.getenv("AGENT_MODEL_STRONG", "qwen3.5:9b")  # OllamaBackend-Default (Agent/Tools)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_CHAT_MODEL = os.getenv("CLAUDE_CHAT_MODEL", "claude-haiku-4-5-20251001")  # Echtzeit-Chat-Antworten

# MLX (großes lokales Modell für Background-Tasks, direkt via mlx_lm — kein Ollama)
MLX_BG_MODEL = os.getenv("MLX_BG_MODEL", "")  # HuggingFace-Repo, z.B. mlx-community/gemma-4-31b-it-4bit

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
# Absender-Allowlist – nur diese Telegram-IDs dürfen mit Alfred reden.
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
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/alfred")

# Web Push (PWA-Benachrichtigungen, Alternative/Ergänzung zu Telegram)
VAPID_PRIVATE_KEY_PATH = os.getenv("VAPID_PRIVATE_KEY_PATH", "data/vapid_private.pem")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIM_EMAIL = os.getenv("VAPID_CLAIM_EMAIL") or OWNER_EMAIL or "admin@localhost"

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

# Google Calendar (OAuth2 – für Alfred → Google Termine schreiben)
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_CALENDAR_ID   = os.getenv("GOOGLE_CALENDAR_ID", "primary")  # 'primary' = Haupt-Kalender
