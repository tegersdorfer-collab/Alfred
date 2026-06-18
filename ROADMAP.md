# Alfred — Roadmap

> Ziel: Ein lokaler, autonomer AI-Concierge der das eigene Leben managt —
> reaktionsschnell, proaktiv, selbst-verbessernd. "Leben auf Autopilot."

---

## Status: Was läuft

| Bereich | Status |
|---------|--------|
| ReAct-Agent mit nativem Tool-Calling | ✅ |
| LLM-Routing (schnell/groß) | ✅ |
| Ollama + Claude API + MLX Backends | ✅ |
| PostgreSQL + pgvector Gedächtnis | ✅ |
| Knowledge-Graph (Entitäten + Relationen) | ✅ |
| Autopilot (Briefing, Review, Anomalien) | ✅ |
| Reflexions-Engine + Meta-Gedächtnis | ✅ |
| Skill-Factory (Code zur Laufzeit) + Prompt-Injection-Schutz | ✅ |
| Alle Concierge-Domänen (Health, Fitness, Habits…) | ✅ |
| Google Calendar (lesen + schreiben) | ✅ |
| HealthKit Background Delivery → Push zu Alfred (kein HTTP-Server mehr) | ✅ |
| Health-Feldmapping vollständig (HR-Min/Avg/Max, HRV, SpO₂, Schlaf-Stages) | ✅ |
| Voice-Transkription in Telegram (Whisper lokal) | ✅ |
| Foto-Analyse in Telegram (llava:7b lokal, Mahlzeiten-Erkennung) | ✅ |
| Dashboard API (FastAPI, 40+ Endpoints) | ✅ |
| Dashboard Frontend (13 Views, PWA) | ✅ |
| Ernährung: Ring-Charts + adaptive Ziele (BMR × Aktivität + Gewichtstrend) | ✅ |
| Live-Chat mit SSE-Streaming | ✅ |
| Echtzeit-Status-Feed | ✅ |
| Web Push (VAPID) | ✅ |
| Automatische Backups | ✅ |
| Task-Suggestions + AI-Zuweisung | ✅ |
| AlphaProgression (Fitness-Periodisierung) | ✅ |
| KZG Rolling Checkpoints (MemGPT-Muster, kein hartes Abschneiden) | ✅ |
| `/health` Systemstatus-Endpoint (DB, Ollama, Telegram, Orchestrator) | ✅ |
| `_safe_task()` — alle Background-Tasks mit Fehlerbehandlung | ✅ |
| Habits-Übersicht: N+1 Queries → 1 Batch-Query (keine 500er unter Last) | ✅ |

---

## Nächste Schritte

### Frontend-Overhaul
- [ ] Neues, cleanes UI-Design (weniger HUD, mehr Übersicht)
- [ ] Bessere Mobile-UX (Swipe-Gesten, Pull-to-Refresh)
- [ ] Dark/Light Mode Toggle

### Health & Fitness
- [ ] Automatische Workout-Empfehlung basierend auf HRV + Schlaf
- [ ] Körpermessungs-Tracking (Umfänge)
- [ ] AlphaProgression — smarte Gewichtsprogression basierend auf Leistungs-Trend
- [ ] Workouts aus HealthKit-Push übernehmen (Swift liefert `workouts`-Array bereits)

### Kommunikation & Benachrichtigungen
- [ ] WhatsApp-Integration (neben Telegram)
- [ ] Push-Notification-Templates (Briefing, Reminder, Anomalien)
- [ ] Smarte Benachrichtigungs-Filterung (kein Spam)

### Wissen & Recherche
- [ ] Tieferes Web-Scraping (Artikel zusammenfassen, Quellen speichern)
- [ ] Automatisches Wissens-Import aus Lesezeichen / Kindle Highlights
- [ ] Periodische Themen-Recherche (Autopilot-gesteuert)

### Autonomie & Selbst-Verbesserung
- [ ] Mehr Autopilot-Trigger (Wetterbasiertes Coaching, Erholungs-Empfehlung)
- [ ] Bessere Lernrate: Alfred passt Ton/Stil an Timos Feedback an
- [ ] Multi-Step Projekte: Alfred plant + führt eigenständig mehrstufige Tasks aus
- [ ] Verification-Bump: Forgetting-Curve Stability erhöhen wenn Timo eine Erinnerung bestätigt
- [ ] Proactive Engagement Decay: Frequenz reduzieren wenn Nachrichten ignoriert werden

### Infrastruktur
- [ ] Automatischer Start nach System-Neustart (launchd)
- [ ] Monitoring: Uptime-Check + Self-Healing bei Absturz
- [ ] HTTPS für Dashboard (Tailscale HTTPS / selbstsigniertes Zertifikat)
- [ ] Embedding-basiertes Tool-Routing (Kategorie-first, semantisches Matching)

### Langfristig / Visionen
- [ ] Voice-Interface: TTS-Antworten (Whisper Input bereits ✅)
- [ ] Eigenes lokales MLX-Modell das auf Timos Daten fine-getuned ist
- [ ] Alfred als MCP-Server für Claude Code (bidirektionale Integration)
- [ ] Batch-Embeddings: mehrere Memories in einem Ollama-Call

---

## Architektur-Prinzipien (unveränderlich)

1. **Lokal first** — Daten verlassen den Mac nicht (außer explizite Cloud-Tools)
2. **Modulare Backends** — LLM, DB, Kommunikation sind austauschbar
3. **Kein Over-Engineering** — einfacher Code > komplexe Abstraktionen
4. **Funktionalität > Ästhetik** — ein Feature das funktioniert > fünf die aussehen
5. **Alfred soll lernen** — jede Interaktion macht ihn besser, nicht nur reaktiver
