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
| Second Brain (brain_notes + brain_links, Graph-View, Wiki-Links, Inbox-Sort) | ✅ |
| Recall Gate (Jaccard-Heuristik vor pgvector-Lookups) | ✅ |
| ADD-only Memory Writes (kein stale-update-Bug möglich) | ✅ |
| Top 3 des Tages (⭐ in Tasks, Widget im Home-Dashboard) | ✅ |
| Daily Resurfacing (täglich rotierende alte Notiz im Home-Dashboard) | ✅ |
| Slipping Tasks (Tasks die >5 Tage nicht angefasst wurden im Home-Dashboard) | ✅ |
| Automatischer Start nach System-Neustart (launchd + Self-Healing bei Crash) | ✅ |
| Warm Profile Injection (KG-User-Entitäten 90s gecacht, top of every prompt) | ✅ |
| Multi-Signal Retrieval (pgvector + Keyword-BM25 fusioniert in search_hybrid) | ✅ |
| Verification-Bump (Ebbinghaus-Stabilität erhöhen wenn Timo Erinnerung bestätigt) | ✅ |
| Tägliche KI-Reflexion 22 Uhr (Wins, Risiken, Muster → brain_notes Daily) | ✅ |
| Workouts aus HealthKit-Push (Swift workouts-Array → fitness.log_workout) | ✅ |
| Importance Triage + Temporales Retrieval-Scoring | ✅ |
| Git-History als Gedächtnis + Proactive Engagement Decay + Tool Discovery | ✅ |
| Dark/Light Mode + Workout-Empfehlung HRV+Schlaf + Monitoring Uptime | ✅ |
| Quotes mit evolving Thoughts + Bessere Lernrate (Ton/Stil-Anpassung) | ✅ |
| Körpermessungs-Tracking (Umfänge + body_measurements Tabelle) | ✅ |
| AlphaProgression (smarte Gewichtsprogression via Session-Ratio) | ✅ |
| Push-Templates + Smarte Dedup-Filterung | ✅ |
| Proaktive Smart-Notifications (fällige Tasks + Habit-Lücken, mittags) | ✅ |
| Web-Scraping + YouTube/Artikel-URL-Zusammenfassung | ✅ |
| Kindle-Highlights-Import (My Clippings.txt → Quotes) | ✅ |
| Periodische Themen-Recherche (Montags-Autopilot) | ✅ |
| Personal Newsletter (Freitags-Digest via Telegram) | ✅ |
| Wetterbasiertes Coaching (morgens, Outdoor-Empfehlung) | ✅ |
| Embedding-basiertes Tool-Routing (TF-IDF Semantic Fallback) | ✅ |
| Eval-Suite (6 Test-Cases + /api/eval/run Endpoint) | ✅ |
| Voice TTS (macOS say-Skill, Stimme Anna/Alex) | ✅ |
| Alfred als MCP-Server (stdio JSON-RPC + HTTP /mcp/) | ✅ |
| Batch-Embeddings (multi-text in einem Ollama-Call) | ✅ |
| Pull-to-Refresh Mobile UX + Memory-Viewer Mahlzeiten-Tab | ✅ |

---

## Nächste Schritte

### Frontend-Overhaul
- [x] Neues, cleanes UI-Design (weniger HUD, mehr Übersicht)
- [x] Bessere Mobile-UX (Swipe-Gesten, Pull-to-Refresh)
- [x] Dark/Light Mode Toggle
- [x] Memory-Viewer: drei Panes (Diary, Knowledge-Graph-Visualisierung, Meals) — wie isair/jarvis
- [x] **Top 3 des Tages**: Im Today-Dashboard genau 3 Tasks per Stern als Tages-Fokus markieren — alles andere ist "nice to have"
- [x] **Daily Resurfacing**: Täglich rotiert ein gespeichertes Zitat / Journal-Eintrag / Kindle-Highlight im Dashboard — verhindert dass gute Notizen nie wieder gelesen werden
- [x] **"Slipping"-Bereich**: Tasks und Projekte die eine konfigurierbare Zeit lang nicht angeschaut wurden tauchen automatisch in einem separaten Dashboard-Bereich auf — kein manueller Reminder nötig

### Health & Fitness
- [x] Automatische Workout-Empfehlung basierend auf HRV + Schlaf
- [x] Körpermessungs-Tracking (Umfänge)
- [x] AlphaProgression — smarte Gewichtsprogression basierend auf Leistungs-Trend
- [x] Workouts aus HealthKit-Push übernehmen (Swift liefert `workouts`-Array bereits)
- [x] Health-kontext-bewusste Ernährungs-Ratschläge: "Soll ich Pizza essen?" → Alfred lädt Mahlzeiten + Kalorienziel + gibt kontextuelle Antwort mit aktuellem Tages-Stand

### Kommunikation & Benachrichtigungen
- [ ] WhatsApp-Integration (neben Telegram)
- [x] Push-Notification-Templates (Briefing, Reminder, Anomalien)
- [x] Smarte Benachrichtigungs-Filterung (kein Spam)
- [x] Proaktive Smart-Notifications: Alfred monitort Bedingungen und pusht aktiv (nicht nur auf Anfrage) — z.B. "du hast diese Woche noch keinen Arzttermin gebucht obwohl du es letzte Woche geplant hast"

### Gedächtnis-Architektur
- [x] **Warm Profile Injection**: Feste Knowledge-Graph-Äste (`user`, `directives`, `world`) — kompakte Zusammenfassung wird bei *jedem* Reply aus SQLite injiziert (kein LLM-Call nötig)
- [x] **Recall Gate**: Keyword-Jaccard-Heuristik vor teuren pgvector-Lookups — wenn Hot-Window die Anfrage bereits ≥50% abdeckt + frisches Tool-Result vorhanden → Memory-Lookup überspringen
- [x] **Importance Triage**: Jedes Memory-Event bekommt Score (keep/archive/review). Events die mehrfach erwähnt werden steigen auf, nie erwähnte fallen ab
- [x] **ADD-only Memory Writes**: Memories werden nie überschrieben, nur angehängt — verhindert "stale update"-Bugs wo das Modell Fakten falsch aktualisiert (Mem0-Pattern)
- [x] **Multi-Signal Retrieval**: Semantic (pgvector) + BM25 (Keyword) + Entity-Matching parallel laufen lassen und fusionieren — jeder Ansatz allein übersieht Dinge
- [x] **Temporales Retrieval-Scoring**: "Was ist mein aktueller Zustand?" vs. "Was habe ich letzten Dienstag gegessen?" unterschiedlich ranken
- [x] **Directives-Branch**: Stehende Anweisungen von Timo ("Erinnere mich immer an X wenn Y", "Antworte nie mit mehr als 3 Sätzen wenn ich unterwegs bin") als eigener Graph-Ast

### Wissen & Recherche
- [x] Tieferes Web-Scraping (Artikel zusammenfassen, Quellen speichern)
- [x] **YouTube → Alfred (fetch_and_summarize_url-Skill)**: Ein Klick auf einer YouTube-Seite schickt Video-URL + Transcript an Alfred → er extrahiert Kernaussagen, bewertet was gut/schlecht/relevant ist, speichert Insights ins Langzeit-Gedächtnis. Kein manuelles Copy-Paste. Funktioniert auch für Artikel (URL senden → Alfred liest + bewertet)
- [x] Automatisches Wissens-Import aus Lesezeichen / Kindle Highlights
- [x] **Quotes mit evolving Thoughts**: Zitate speichern + über Zeit mehrere Gedanken dazu loggen (Feed unter jedem Zitat) — sichtbar wie sich das Denken über Monate verändert
- [x] Periodische Themen-Recherche (Autopilot-gesteuert)
- [x] **Personal Newsletter**: Wiederkehrende Recherche-Queries → E-Mail-Digest ("fasse KI-News die zu meinen Projekten passen wöchentlich zusammen") — wie Khoj
- [x] **Git-History als Gedächtnis**: Commit-Log importieren → "Woran habe ich im März gearbeitet?" wird beantwortbar; Produktivitätsmuster aus Commit-Dichte

### Autonomie & Selbst-Verbesserung
- [x] Mehr Autopilot-Trigger (Wetterbasiertes Coaching, Erholungs-Empfehlung)
- [x] Bessere Lernrate: Alfred passt Ton/Stil an Timos Feedback an
- [x] Multi-Step Projekte: Alfred plant + führt eigenständig mehrstufige Tasks aus
- [x] Verification-Bump: Forgetting-Curve Stability erhöhen wenn Timo eine Erinnerung bestätigt
- [x] Proactive Engagement Decay: Frequenz reduzieren wenn Nachrichten ignoriert werden
- [x] **Tägliche KI-Reflexion mit Pattern-Detection**: End-of-Day LLM-Run: Wins, Risiken, wiederkehrende Muster über alle Daten (Commits, Kalender, Health, Habits)
- [x] **Claude Code Subprocess**: "Alfred, bau X" → spawnt `claude`-Subprocess im Hintergrund, Push-Notification wenn fertig
- [x] **Tool Discovery Escape Hatch**: Alfred bekommt ein `refresh_tools`-Tool das es mid-Reply aufrufen kann wenn es eine fehlende Fähigkeit vermutet — erweitert sich selbst
- [x] **Embedding-basiertes Tool-Routing**: Alle Tools registrieren, per Query semantisch ranken, nur Top-N in Context injizieren → beliebig viele Tools ohne Context-Overhead
- [x] **Background Review Loop (Hermes-Pattern)**: Nach jedem Turn läuft Fork-Agent der entscheidet ob Skill/Memory gespeichert wird — "BE ACTIVE"-Direktive, non-blocking
- [x] **SKILL.md Prozedur-System**: Skills als Markdown-Dateien mit Frontmatter (Trigger, Platform-Gates), automatisch in System-Prompt injiziert wenn relevant
- [x] **Subagent Delegation**: `delegate_task`-Tool spawnt isolierten Kind-Agenten mit eigenem Context, eingeschränktem Toolset, Timeout — kein Rekursionsrisiko

### Infrastruktur
- [x] Automatischer Start nach System-Neustart (launchd + KeepAlive Crash-Recovery)
- [x] Monitoring: Uptime-Check + Self-Healing bei Absturz
- [ ] HTTPS für Dashboard (Tailscale HTTPS / selbstsigniertes Zertifikat)
- [ ] **Free Dictation Side-Mode**: Hotkey halten → sprechen → loslassen → Text erscheint in vorderstem App (offline, kein Abo — Alternative zu WisprFlow)
- [x] **Eval-Suite**: Benannte Test-Cases für Agent-Verhalten ("leugnet nicht Langzeit-Gedächtnis zu haben", "überspringt Recall wenn Context frisch", "kettet Search → Fetch korrekt") mit Track-Record

### Langfristig / Visionen
- [x] Voice-Interface: TTS-Antworten (Whisper Input bereits ✅)
- [ ] Eigenes lokales MLX-Modell das auf Timos Daten fine-getuned ist
- [x] Alfred als MCP-Server für Claude Code (bidirektionale Integration)
- [x] Batch-Embeddings: mehrere Memories in einem Ollama-Call
- [ ] **Ambient Listening Mode**: Alfred hört passiv mit, baut Rolling-Context aus Umgebungsgesprächen — bei Wake-Word antwortet er bereits im Kontext ohne Wiederholung
- [ ] **Google Takeout Location-Timeline**: Bewegungshistorie importieren → Muster-Detection ("du gehst immer dienstags ins Gym — soll ich das einplanen?")

---

## Architektur-Prinzipien (unveränderlich)

1. **Lokal first** — Daten verlassen den Mac nicht (außer explizite Cloud-Tools)
2. **Modulare Backends** — LLM, DB, Kommunikation sind austauschbar
3. **Kein Over-Engineering** — einfacher Code > komplexe Abstraktionen
4. **Funktionalität > Ästhetik** — ein Feature das funktioniert > fünf die aussehen
5. **Alfred soll lernen** — jede Interaktion macht ihn besser, nicht nur reaktiver
