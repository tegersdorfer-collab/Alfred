# Alfred 2.0 — Von reaktivem Bot zu autonomem AI-Concierge

> Ziel: Aus einem reaktiven Telegram-Bot ein High-End, selbst-verbesserndes
> Lebens-Betriebssystem machen. "Leben auf Autopilot."

## Leitprinzipien
1. **Agentisch** – Alfred entscheidet selbst welche Tools er nutzt (echtes Function-Calling), nicht starre Regex-Regeln.
2. **Proaktiv & autonom** – ein echtes Autopilot-System mit eigener Agenda, zeitbewussten Aktivitäten, Anomalie-Erkennung.
3. **Selbst-verbessernd** – Reflexions-Engine, Meta-Gedächtnis über Timos Vorlieben, Verhaltensanpassung.
4. **Schnell** – Streaming-Antworten, warmes Modell, paralleler Kontextaufbau.
5. **Alles managen** – Health, Fitness, Habits, Ernährung, Journal, Tasks, Kalender, Ziele, Wissen.
6. **High-End UI** – mobil-first interaktives Dashboard wie ein VIP-Produkt, kein Schulprojekt.

## Architektur-Phasen

### Phase A — Datenfundament
- `core/db.py`: zentraler Connection-Pool, Migrations-Runner
- Neue Tabellen (alfred DB): habits, habit_logs, workouts, exercises, workout_sets,
  training_plans, journal_entries, meals, goals, agenda, reflections, chat_messages,
  events_log, metrics_snapshots

### Phase B — Agent-Kern (Function-Calling)
- `core/tools.py`: Tool-Registry mit JSON-Schemas
- `core/agent.py`: ReAct-Loop, Multi-Step-Tool-Ausführung, Qwen3 native tool calls

### Phase C — Domänen-Tools (Concierge-Skills)
- Habits, Fitness/Workout, Ernährung, Journal, Ziele, Wetter, Kalender-Schreiben, Notizen, Finanzen

### Phase D — Speed
- Token-Streaming nach Telegram (live-edit)
- keep_alive (Modell warm), paralleler Kontextaufbau, Embedding-Cache, schneller Router (llama3.2:3b)

### Phase E — Autopilot (autonome Engine)
- `core/autopilot.py`: Agenda-Queue, zeitbewusste Aktivitäten
  (Morgen-Briefing, Abend-Review, Health-Anomalien, Ziel-Checkins, Recherche)

### Phase F — Selbst-Verbesserung
- `core/reflection.py`: Gesprächsanalyse, Meta-Memory, Verhaltensanpassung, Selbstkritik

### Phase G — Dashboard-Backend
- `web/server.py` massiv erweitern: REST für alle Domänen + Chat (2-Wege) + Aktionen + SSE

### Phase H — Dashboard-Frontend
- Mobil-first PWA, Multi-View: Command Center, Chat, Health, Fitness-App, Habits,
  Tasks, Kalender, Journal, Ernährung, Ziele, Memory-Browser, Alfred-Mind, Analytics, Settings

### Phase I — Integration & Test
