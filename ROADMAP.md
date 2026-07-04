# Alfred — Roadmap

> **Ziel**: Ein lokaler, autonomer AI-Concierge der das eigene Leben managt —
> reaktionsschnell, proaktiv, selbst-verbessernd. *"Leben auf Autopilot."*

---

## Fertig ✅

### Agent-Kern
- ReAct-Agent mit nativem Tool-Calling (57 Tools)
- LLM-Routing: Claude Haiku (Chat) + Ollama qwen3.5:9b (Background)
- Ollama + Claude API Backends (austauschbar)
- Streaming: Token-Streaming an Telegram + Dashboard (SSE)
- `_safe_task()` — alle Background-Tasks mit Fehlerbehandlung
- Subagent Delegation (`delegate_task`) — isolierter Kind-Agent, eigener Context, Timeout
- LLM-Fallback: Claude API ausgefallen → lokales Ollama übernimmt transparent
  (90s-Timeout, 180s-Cooldown, Ausfall im Fehler-Widget sichtbar)
- Generatives UI (Phase 2, erster Durchstich): Tool-Aufrufe (get_health) lösen automatisch
  Widgets im Tauri-Desktop-Client aus — deterministische Tool→Widget-Zuordnung
  (core/ui_state.py), neuer SSE-Kanal (/api/ui/stream, /api/ui/current), Sleep-Widget
  ersetzt den HUD-Ring bei Treffer und schaltet bei irrelevanten Turns zurück

### Gedächtnis-Architektur
- PostgreSQL + pgvector Langzeitgedächtnis
- Knowledge-Graph (kg_entities + kg_relations)
- KZG Rolling Checkpoints (MemGPT-Muster, kein hartes Abschneiden)
- ADD-only Memory Writes (kein stale-update-Bug)
- Recall Gate (Jaccard-Heuristik vor pgvector-Lookups)
- Multi-Signal Retrieval (pgvector + Keyword-BM25 fusioniert)
- Temporales Retrieval-Scoring ("heute" vs. "letzten März")
- Warm Profile Injection (KG-User-Entitäten 90s gecacht, top of system prompt)
- Verification-Bump (Ebbinghaus-Stabilität steigt bei Bestätigung)
- Importance Triage (recall_count ≥ 3 → +0.1, nie recalled + 14d → -0.05)

### Selbst-Verbesserung
- Skill-Factory (Python-Skills zur Laufzeit, AST-validiert, Git-committed)
- **Background Review Loop** (Hermes-Pattern): Fork-Agent nach jedem Turn, `BE ACTIVE`-Direktive
- **SKILL.md Prozedur-System**: Natürlichsprachliche Skills mit Frontmatter, Trigger-basierte Injektion
- Reflexions-Engine: Ton/Stil-Anpassung, Längen-Kalibrierung
- Proactive Engagement Decay: Frequenz sinkt wenn Nachrichten ignoriert werden
- Embedding-basiertes Tool-Routing (TF-IDF Semantic Fallback)
- Tool Discovery Escape Hatch (`refresh_tools`)
- Claude Code Subprocess: "Alfred, bau X" → spawnt `claude`-Subprocess

### Autopilot
- Morgen-Briefing, Abend-Review, Wöchentlicher Rückblick
- Tägliche KI-Reflexion 22 Uhr (Wins, Risiken, Muster → brain_notes)
- Workout-Empfehlung basierend auf HRV + Schlaf
- Smart Notifications (fällige Tasks + Habit-Lücken, mittags)
- Wetterbasiertes Coaching (morgens, Outdoor-Empfehlung)
- Wöchentliche Themen-Recherche (Montags-Autopilot)
- Personal Newsletter (Freitags-Digest via Telegram)
- Monitoring: Uptime-Check + Push-Notification bei Fehlern

### Domänen
- HealthKit Background-Push von iOS (kein HTTP-Server mehr)
- Health-Feldmapping vollständig (HR-Min/Avg/Max, HRV, SpO₂, Schlaf-Stages)
- Workouts aus HealthKit-Push (Swift workouts-Array → fitness.log_workout)
- AlphaProgression (HRV/Schlaf-basierte Gewichtsempfehlung)
- Körpermessungs-Tracking (Umfänge, body_measurements Tabelle)
- Ernährung: adaptive Ziele (BMR × Aktivität + Gewichtstrend-Regression)
- Google Calendar (lesen + schreiben)
- Voice-Transkription in Telegram (Whisper lokal)
- Foto-Analyse in Telegram (llava:7b, Mahlzeiten-Erkennung)
- Second Brain (brain_notes, Kategorien, Wiki-Links, Graph-View)
- Quotes mit evolving Thoughts (Gedanken über Zeit anfügen)
- Kindle-Highlights-Import (My Clippings.txt → Quotes)
- Web-Scraping + YouTube/Artikel-URL-Zusammenfassung
- Git-History als Gedächtnis (Commit-Log → brain_notes)
- Periodische Themen-Recherche + Research-Query-Skill

### Dashboard & Infrastruktur
- PWA (14 Views, installierbar, Service Worker)
- Dark/Light Mode, Pull-to-Refresh, Mobile-UX
- Memory-Viewer (Diary, Knowledge-Graph vis.js, Mahlzeiten)
- Top-3 Tages-Fokus, Daily Resurfacing, Slipping Tasks
- Web Push (VAPID) + Push-Templates + Dedup-Filterung
- Eval-Suite (6 Test-Cases, `/api/eval/run`)
- Alfred als MCP-Server (stdio JSON-RPC + HTTP `/mcp/`)
- Eval-Suite v2: echter Agent-Lauf (prompt_builder + agent.run), Dry-Run-Tools,
  must_call_tool-Check, Timeout pro Case — deckte den warm_profile-Crash auf
- LLM-Usage-Tracking: Token + Kosten pro Call (`llm_usage`), `/api/usage`,
  API-Kosten-Karte in Analytics, `api_costs`-Tool
- warm_profile-Fix (literales % in SQL crashte jeden Prompt-Build) +
  prompt_builder degradiert bei Kontext-Fehlern statt den Turn zu killen
- Batch-Embeddings (multi-text in einem Ollama-Call)
- Automatischer Start nach Neustart (launchd + KeepAlive)
- Automatische DB-Backups
- Neues UI-Design (dunklere Tokens, cleaner Home, bessere Typografie)

### Native iOS-Apps (SwiftUI)
- **BodyOS** — Training (Alfred-Sessions aus HRV/Schlaf) + Ernährung (Foto-Makros) + HealthKit-Push
- **BrainOS** — Second Brain: Wiki-Links, Force-directed Graph (SwiftUI Canvas, eigene Physik)
- **FlowOS** — Tasks + Kalender + Habits + Fokus-Timer
- Gemeinsamer `AlfredClient` pro App: `waitsForConnectivity` + Retry → übersteht Tailscale-Aussetzer
- Details in `apps/README.md` (konsolidiert aus ursprünglich 5 geplanten Apps)

### Code-Architektur
- Orchestrator aufgeteilt: `prompt_builder`, `message_handler`, `idle_loop`
- `web/api.py` in Router-Module pro Domäne gesplittet (`web/routers/`)
- `core/skills.py` in Kategorie-Pakete gesplittet (`core/skills/`); CTX in `core/skill_context.py` (mutate-bind)
- GC-sichere Background-Tasks (`_bg_tasks` Liste mit Referenzen)
- DB-Fehler beim Start bricht Start ab (kein stiller Datenverlust)
- `api.py` nutzt `orch.chat_llm` direkt (toter `self.llm`-Alias entfernt)
- Dashboard bindet auf `0.0.0.0` — Tailscale-Drop kann Server nicht mehr auf localhost zwingen
- Embedding-Modell `qwen3-embedding:0.6b`; Python-Pfad in `start.sh` dynamisch aufgelöst

---

## Offen — externe Abhängigkeiten

Diese Items brauchen externe Infrastruktur oder Hardware die nicht im Code lösbar ist:

| Item | Blockiert durch |
|------|----------------|
| WhatsApp-Integration | Meta Business API + verifizierte Nummer |
| HTTPS für Dashboard | Tailscale-Zertifikat oder mkcert-Setup |
| Free Dictation Side-Mode | macOS Accessibility-Daemon (Hotkey → Whisper → Tastatureingabe) |
| Eigenes MLX-Modell | Fine-Tuning Compute + Trainingsdaten |
| Ambient Listening Mode | Always-on Mikrofon (Privacy-kritisch, Hardware) |
| Google Takeout Location-Timeline | Timos persönliche Takeout-Datei |

---

## Architektur-Prinzipien

1. **Lokal first** — Daten verlassen den Mac nicht (außer explizite Cloud-Tools wie Claude API)
2. **Modulare Backends** — LLM, DB, Kommunikation sind austauschbar
3. **Kein Over-Engineering** — einfacher Code > komplexe Abstraktionen
4. **Funktionalität > Ästhetik** — ein Feature das funktioniert > fünf die aussehen
5. **Alfred soll lernen** — jede Interaktion macht ihn besser, nicht nur reaktiver
