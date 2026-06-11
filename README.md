# Alfred 🤖

Persönlicher, autonomer AI-Concierge — läuft lokal auf einem Mac (Apple Silicon),
spricht über Telegram und ein eigenes mobil-first Dashboard.

## Features
- **Agentischer Kern** mit nativem Tool-Calling (Qwen3.5 via Ollama) – 25+ Tools
- **Autopilot**: Morgen-Briefing, Abend-Review, Health-Anomalie-Erkennung, proaktive Nachrichten
- **Selbst-Verbesserung**: Reflexion, Meta-Gedächtnis, Verhaltensanpassung
- **Gedächtnis**: Kurzzeit (KZG) + Langzeit (pgvector) mit Komprimierung & Konsolidierung
- **Concierge-Domänen**: Tasks (mit Unteraufgaben), Habits, Fitness/Gym, Ernährung,
  Journal, Ziele, Kalender, Reminder, Wetter, Web-Suche
- **Dashboard** (FastAPI + PWA): 14 interaktive Views, Live-Chat mit dem Agent, Charts

## Stack
- Python 3.14 (asyncio)
- Ollama (qwen3:14b + llama3.2:3b + nomic-embed-text)
- PostgreSQL + pgvector
- python-telegram-bot, FastAPI/uvicorn

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env          # Werte eintragen
createdb alfred               # PostgreSQL-DB anlegen (pgvector-Extension nötig)
./start.sh                    # startet Alfred + Dashboard (Port 7779)
```

## Architektur
- `main.py` – Entry Point (Orchestrator + Dashboard im selben Prozess)
- `orchestrator.py` – Koordinator (Agent, Gedächtnis, Autopilot, Reflexion)
- `core/` – Agent, Tools, DB-Pool, Autopilot, Reflexion, Skills
- `domains/` – Habits, Fitness, Ernährung, Journal, Ziele, Wetter, Tasks
- `memory/` – KZG, LZG, Compressor, Consolidator
- `communication/` – Telegram-Channel (austauschbar)
- `llm/` – Ollama / Claude Provider (austauschbar)
- `web/` – Dashboard (FastAPI API + PWA-Frontend)
