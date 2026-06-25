# Alfred

Persönlicher, autonomer AI-Concierge — läuft vollständig lokal auf einem Mac (Apple Silicon),
erreichbar über Telegram und ein mobil-first PWA-Dashboard.

---

## Was Alfred kann

### Agent-Kern
- **ReAct-Loop** mit 57 Tools, multi-step Ausführung, parallelem Tool-Calling
- **LLM-Backends**: Ollama (qwen3.5:9b), Claude API (Haiku für Chat, Sonnet für komplexe Tasks)
- **Subagent-Delegation**: `delegate_task` spawnt isolierte Kind-Agenten für umfangreiche Teilaufgaben
- **Token-Streaming** an Telegram + Dashboard (SSE)

### Gedächtnis-Architektur
| Schicht | Technologie | Funktion |
|---------|-------------|---------|
| **KZG** (Kurzzeitgedächtnis) | In-Memory + Rolling Checkpoints | Aktives Gesprächsfenster, ältere Turns via LLM komprimiert |
| **LZG** (Langzeitgedächtnis) | PostgreSQL + pgvector | Semantische Suche, Ebbinghaus Forgetting-Curve |
| **Knowledge-Graph** | kg_entities / kg_relations | Entitäten, Relationen, Directives, Warm-Profile |
| **SKILL.md** | Markdown + Frontmatter | Natürlichsprachliche Prozeduren, automatisch injiziert |

- **Recall Gate**: Jaccard-Heuristik überspringt pgvector wenn KZG bereits ausreichend Kontext hat
- **Multi-Signal Retrieval**: pgvector + Keyword-BM25 fusioniert
- **Warm Profile Injection**: KG-User-Entitäten (90s gecacht) top of every system prompt
- **Verification-Bump**: Ebbinghaus-Stabilität steigt wenn Timo eine Erinnerung bestätigt
- **Background Review Loop**: Nach jedem Turn läuft ein Fork-Agent der automatisch Skills/Memories speichert

### Selbst-Verbesserung
- **Skill-Factory**: Alfred schreibt Python-Skills zur Laufzeit (AST-validiert, sofort aktiv)
- **SKILL.md Prozeduren**: Natürlichsprachliche Workflows werden automatisch aus Konversationen gelernt
- **Reflexions-Engine**: Ton/Stil-Anpassung, Längen-Kalibrierung, Proactive Engagement Decay
- **Background Review Loop** (Hermes-Pattern): `BE ACTIVE` — die meisten Turns speichern etwas
- **Embedding-basiertes Tool-Routing**: TF-IDF Semantic Fallback, max 14 Tools im Context

### Autopilot & Proaktivität
| Trigger | Was passiert |
|---------|-------------|
| 6–9h täglich | Morgen-Briefing mit Kalender, Wetter, Habits |
| 20–21h täglich | Abend-Review (Tages-Zusammenfassung) |
| 22–23h täglich | KI-Reflexion: Wins, Risiken, Muster |
| 7–10h täglich | Workout-Empfehlung basierend auf HRV + Schlaf |
| 12–14h täglich | Smart Notifications: fällige Tasks, Habit-Lücken |
| 7–10h täglich | Wetterbasiertes Coaching |
| Montags 8–9h | Wöchentliche Themen-Recherche |
| Freitags 17–18h | Personal Newsletter (Telegram-Digest) |

### Domänen (Concierge-Skills)
| Domäne | Highlights |
|--------|-----------|
| **Health** | HealthKit Background-Push von iOS, HR-Min/Avg/Max, HRV, SpO₂, Schlaf-Stages, Schritte |
| **Fitness** | Workout-Log, AlphaProgression (HRV/Schlaf-basierte Gewichtsempfehlung), Muskelgruppen |
| **Körpermessungen** | Umfänge (Taille, Brust, Hüfte, Bizeps etc.), Trend-Vergleich |
| **Ernährung** | Mahlzeiten, Makros, adaptiver Kalorie-Rechner (BMR × Aktivität + Gewichtstrend) |
| **Habits** | Streak, Commit-Graph, Kategorien |
| **Tasks** | Unteraufgaben, AI-Zuweisung, Slipping-Detection, Top-3-Fokus |
| **Journal** | KI-Prompts, Stimmung/Energie |
| **Kalender** | Google Calendar lesen + schreiben |
| **Ziele** | Progress-Tracking, Deadline-Erinnerungen |
| **Second Brain** | brain_notes, Kategorien (inbox/project/area/resource/daily/quote), Wiki-Links, Graph-View |
| **Wissen** | Web-Suche, URL-Zusammenfassung, YouTube-Transkript, Kindle-Highlights-Import |

### Dashboard (PWA)
- **14 Views**: Home, Chat, Health, Habits, Tasks, Kalender, Ernährung, Journal, Ziele, Brain, Memory, A.I. Mind, Analytics, Settings
- **Live-Chat** mit SSE-Streaming direkt zum Agent-Kern
- **Dark/Light Mode**, Pull-to-Refresh, installierbar als Homescreen-App
- **Memory-Viewer**: Diary, Knowledge-Graph (vis.js), Mahlzeiten
- **Home**: Top-3 Fokus, Slipping Tasks, Daily Resurfacing, Wetter, Health-Metriken
- **Eval-Suite**: `/api/eval/run` — 6 benannte Test-Cases für Agent-Verhalten
- **MCP-Server**: Alfred als Tool-Provider für Claude Code (`/mcp/` Endpunkte)

### Native iOS-Apps
Drei fokussierte SwiftUI-Apps gegen dieselbe FastAPI (`:7779`), erreichbar
über Tailscale. Details + Build-/Deploy-Anleitung in [`apps/README.md`](apps/README.md).

| App | Bündelt | Highlights |
|-----|---------|-----------|
| **BodyOS** | Training + Ernährung + Health | Alfred-generierte Sessions (HRV/Schlaf), Foto-Makros, HealthKit-Push |
| **BrainOS** | Second Brain | Wiki-Links, Force-directed Graph (SwiftUI Canvas), Quick Capture |
| **FlowOS** | Tasks + Kalender + Habits | Today-View, Fokus-Timer, Habit-Grid |

---

## Stack

| Schicht | Technologie |
|---------|------------|
| Sprache | Python 3.14 (asyncio) |
| LLM | Ollama (qwen3.5:9b) · Claude API (Haiku/Sonnet) |
| DB | PostgreSQL 16 + pgvector |
| Backend | FastAPI + uvicorn |
| Frontend | Vanilla JS PWA (Chart.js, vis.js, marked.js) · 3 native SwiftUI-Apps |
| Kommunikation | python-telegram-bot · Voice (Whisper lokal) · Fotos (llava:7b) |
| Health-Import | Swift-App → HealthKit Background Delivery → HTTP Push |
| Prozess-Management | launchd + KeepAlive (Auto-Restart nach Crash) |

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env       # API-Keys & DB-Config eintragen
createdb alfred            # PostgreSQL + pgvector Extension
python3 main.py            # Alfred + Dashboard starten (Port 7779)
```

---

## Architektur

```
Alfred/
├── main.py                  # Entry Point — Orchestrator + Dashboard im selben Prozess
├── orchestrator.py          # Schlanke Fassade: Init, Start/Stop, öffentliche API
│
├── core/
│   ├── prompt_builder.py    # System-Prompt (Memory, KG, Skills, Recall Gate)
│   ├── message_handler.py   # Nachrichtenverarbeitung, Streaming, Post-Turn Learning
│   ├── idle_loop.py         # Autopilot-Ticks, Maintenance, Monitoring
│   ├── agent.py             # ReAct-Loop, Tool-Calling
│   ├── autopilot.py         # Zeitbewusste autonome Aktivitäten
│   ├── background_review.py # Hermes-Pattern: Fork-Agent lernt nach jedem Turn
│   ├── skill_factory.py     # Python-Skills dynamisch erstellen/laden
│   ├── skill_md.py          # SKILL.md Prozeduren: Trigger-basierte System-Prompt-Injektion
│   ├── reflection.py        # Verhaltensanpassung, Stil-Kalibrierung
│   ├── eval_suite.py        # Benannte Test-Cases für Agent-Verhalten
│   ├── push.py              # Web Push (VAPID) + Templates + Dedup
│   └── tools.py             # Tool-Registry + semantisches Routing
│
├── memory/
│   ├── kzg.py               # Kurzzeitgedächtnis + Rolling Checkpoints
│   ├── lzg.py               # Langzeitgedächtnis (pgvector, hybrid search)
│   ├── knowledge.py         # Knowledge-Graph + Warm-Profile
│   └── forgetting.py        # Ebbinghaus Forgetting-Curve + Importance Triage
│
├── domains/                 # Health, Fitness, Body, Ernährung, Habits, Tasks,
│                            # Journal, Ziele, Second Brain, Calendar, Weather …
│
├── llm/                     # Ollama / Claude Provider (austauschbar über base.py)
├── communication/           # Telegram-Channel
├── tools/                   # WebSearch, DashboardReader, Delegate (Subagents)
├── skills/                  # SKILL.md Prozedur-Dateien (auto-generiert)
│
├── web/
│   ├── api.py               # FastAPI App-Factory: bindet Router aus web/routers/
│   ├── routers/             # REST + SSE pro Domäne (tasks, brain, fitness, …)
│   ├── mcp_server.py        # Alfred als MCP-Server (stdio JSON-RPC)
│   ├── index.html           # PWA-Frontend (Single-File, ~2400 Zeilen)
│   └── sw.js                # Service Worker
│
└── apps/                    # Native iOS-Apps (SwiftUI) — siehe apps/README.md
    ├── BodyOS/              # Training + Ernährung + Health
    ├── BrainOS/             # Second Brain (Notizen, Graph)
    └── FlowOS/              # Tasks + Kalender + Habits
```
