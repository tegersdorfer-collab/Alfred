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
| Skill-Factory (Code zur Laufzeit) | ✅ |
| Alle Concierge-Domänen (Health, Fitness, Habits…) | ✅ |
| Google Calendar (lesen + schreiben) | ✅ |
| HealthKit-Push von iPhone (Swift) | ✅ |
| Dashboard API (FastAPI, 40+ Endpoints) | ✅ |
| Dashboard Frontend (13 Views, PWA) | ✅ |
| Live-Chat mit SSE-Streaming | ✅ |
| Echtzeit-Status-Feed | ✅ |
| Web Push (VAPID) | ✅ |
| Automatische Backups | ✅ |
| Task-Suggestions + AI-Zuweisung | ✅ |
| AlphaProgression (Fitness-Periodisierung) | ✅ |

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

### Infrastruktur
- [ ] Automatischer Start nach System-Neustart (launchd)
- [ ] Monitoring: Uptime-Check + Self-Healing bei Absturz
- [ ] Remote-Access über Tailscale absichern (read-only token für Dashboard)

### Langfristig / Visionen
- [ ] Voice-Interface (Whisper → Alfred → TTS)
- [ ] Kamera-Integration (Mahlzeiten-Erkennung per Foto)
- [ ] Eigenes lokales MLX-Modell das auf Timos Daten fine-getuned ist
- [ ] Alfred als MCP-Server für Claude Code (bidirektionale Integration)

---

## Architektur-Prinzipien (unveränderlich)

1. **Lokal first** — Daten verlassen den Mac nicht (außer explizite Cloud-Tools)
2. **Modulare Backends** — LLM, DB, Kommunikation sind austauschbar
3. **Kein Over-Engineering** — einfacher Code > komplexe Abstraktionen
4. **Funktionalität > Ästhetik** — ein Feature das funktioniert > fünf die aussehen
5. **Alfred soll lernen** — jede Interaktion macht ihn besser, nicht nur reaktiver
