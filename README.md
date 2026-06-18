# Alfred 🤖

Persönlicher, autonomer AI-Concierge — läuft lokal auf einem Mac (Apple Silicon),
spricht über Telegram und ein eigenes mobil-first Dashboard.

## Features

### Agent-Kern
- **Function-Calling** via ReAct-Loop — 25+ Tools, multi-step Ausführung
- **LLM-Backends**: Ollama (qwen3.5:9b / gemma4:31b), Claude API (Haiku/Sonnet), MLX lokal
- **Schneller Router** (`llm_gate`): einfache Anfragen → kleines Modell, komplex → großes
- **Streaming**: Token-Streaming an Telegram + Dashboard (SSE)

### Autopilot & Proaktivität
- Morgen-Briefing, Abend-Review, wöchentlicher Rückblick
- Proaktive Nachrichten bei Health-Anomalien, Ziel-Deadlines, Habit-Lücken
- Eigene Agenda-Queue mit zeitbewussten Aktivitäten

### Selbst-Verbesserung
- **Reflexion**: Gesprächsanalyse, Meta-Notizen, Verhaltensanpassung
- **Skill-Factory**: Alfred schreibt/löscht eigene Python-Skills zur Laufzeit
- **Code-Write**: selbst-modifizierender Code mit Revert-Funktion

### Gedächtnis
- **KZG** (Kurzzeit): rollendes Kontext-Fenster
- **LZG** (Langzeit): pgvector Embeddings, semantische Suche
- **Knowledge-Graph**: Entitäten + Relationen (kg_entities / kg_relations)
- Memory-Extraktion aus Chat & Journal, Konsolidierung, Forgetting-Curve

### Domänen (Concierge-Skills)
| Domäne | Highlights |
|--------|-----------|
| **Health** | HealthKit-Push von iOS, steps, HRV, Schlaf, Gewicht |
| **Fitness** | Workout-Log, Satz-Tracking, Muskelgruppen-Analyse, AlphaProgression |
| **Ernährung** | Mahlzeiten, Makros, adaptiver Kalorie-Rechner (Bulk-Trend) |
| **Habits** | Streak, Commit-Graph, Drag-Reihenfolge, Kategorien |
| **Tasks** | Unteraufgaben, Fortschritt, AI-Zuweisung, Task-Suggestions |
| **Journal** | KI-Prompts, Stimmung/Energie, Themen-Cloud |
| **Kalender** | Google Calendar (lesen + schreiben via gcal_writer) |
| **Ziele** | Progress-Tracking, Deadline-Erinnerungen |
| **Wetter** | Forecast via Open-Meteo |
| **Wissen** | Web-Suche, URL-Zusammenfassung |

### Dashboard (PWA)
- **13 Views**: Home, Chat, Health, Habits, Tasks, Kalender, Ernährung, Journal, Ziele, Memory, A.I. Mind, Analytics, Settings
- **Live-Chat** mit SSE-Streaming direkt zum Agent-Kern
- **Live-Status**: Echtzeit-Aktivitäts-Feed (was Alfred gerade macht)
- **Charts**: Health-Trends, Schlaf, Schritte, Habits-Konsistenz, Wissens-Graph (vis.js)
- **Web Push**: PWA-Benachrichtigungen (VAPID)
- **Backup**: automatische & manuelle DB-Backups
- **Self-Changes**: Diff-Viewer + Revert für alle Selbst-Änderungen

## Stack

| Schicht | Tech |
|---------|------|
| Sprache | Python 3.14 (asyncio) |
| LLM | Ollama · Claude API · MLX (lokal) |
| DB | PostgreSQL 16 + pgvector |
| Backend | FastAPI + uvicorn |
| Frontend | Vanilla JS PWA (Chart.js, vis.js) |
| Kommunikation | python-telegram-bot |
| Health-Import | Swift-App → HTTP Push |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # API-Keys & DB-Config eintragen
createdb alfred               # PostgreSQL + pgvector Extension
./start.sh                    # Alfred + Dashboard starten (Port 7779)
```

## Architektur

```
Alfred/
├── main.py              # Entry Point — Orchestrator + Dashboard im selben Prozess
├── orchestrator.py      # Koordinator (Agent, Gedächtnis, Autopilot, Reflexion)
├── core/
│   ├── agent.py         # ReAct-Loop, Tool-Calling
│   ├── autopilot.py     # Zeitbewusste autonome Aktivitäten
│   ├── reflection.py    # Gesprächs-Analyse, Meta-Memory
│   ├── skill_factory.py # Dynamische Skill-Erstellung/-Löschung
│   ├── llm_gate.py      # Schnell-Router (kleines vs. großes Modell)
│   ├── db.py            # PostgreSQL Pool + Migrations
│   └── tools.py         # Tool-Registry
├── domains/             # Habits, Fitness, Ernährung, Journal, Ziele, Wetter, Tasks …
├── memory/              # KZG, LZG (pgvector), Knowledge-Graph, Consolidator
├── llm/                 # Ollama / Claude / MLX Provider (austauschbar)
├── communication/       # Telegram-Channel
└── web/
    ├── api.py           # FastAPI REST + SSE Endpoints
    ├── index.html       # PWA-Frontend (Single-File)
    └── sw.js            # Service Worker
```
