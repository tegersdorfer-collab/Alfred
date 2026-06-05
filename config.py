import os
from dotenv import load_dotenv

load_dotenv()

# LLM
OLLAMA_MODEL      = os.getenv("OLLAMA_MODEL", "qwen3:14b")
OLLAMA_FAST_MODEL = os.getenv("OLLAMA_FAST_MODEL", "llama3.2:3b")  # schneller Router/Klassifikation
OLLAMA_BASE_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")          # Modell warm halten
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = "claude-haiku-4-5"  # Für schwere Tasks

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# Besitzer (persönliche Daten – aus .env, NICHT im Repo)
OWNER_NAME     = os.getenv("OWNER_NAME", "Timo")
OWNER_EMAIL    = os.getenv("OWNER_EMAIL", "")
OWNER_TIMEZONE = os.getenv("OWNER_TIMEZONE", "Europe/Berlin")

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
PROACTIVE_INTERVAL        = 30 * 60  # 30 Min Mindestabstand danach

# Memory
LZG_EMBED_MODEL  = "nomic-embed-text"   # Lokales Embedding via Ollama
LZG_TOP_K        = 5                    # Wie viele Memories beim Start laden
KZG_MAX_TURNS    = 20                   # Max Turns im Kurzzeitgedächtnis

# Search
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
