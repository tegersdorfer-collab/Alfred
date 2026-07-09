# Code-Qualitäts-Pass (2026-07-09, laufender Loop)

> Auftrag: gesamte Codebase Modul für Modul auf sehr gutes Niveau heben.
> Vorgehen pro Modul: lesen → tote/duplizierte Pfade raus, Fehlerbehandlung,
> Struktur, fehlende Tests ergänzen → Tests laufen lassen → committen.
> Regeln: Verhalten NICHT ändern (reiner Qualitäts-Pass), kleine Commits,
> 380-Tests-Baseline darf nie sinken. Kein Over-Engineering (Prinzip #3).

## Baseline
- 380 Tests grün (1.8s), Branch `robot/x5-autonomy`
- Smells: 73× `except Exception: pass` (stumm), 13× `print` statt Logging
- f-string-SQL in goals.py/calendar.py geprüft → sicher (nur Spaltenfragmente)

## Arbeitsliste (Reihenfolge = Kopplung/Risiko)
- [x] 1. core/db.py — Pool-Vergiftung durch tote Connections gefixt (putconn close=broken),
      Retry-once bei Verbindungsverlust, thread-sicheres init_pool, json-Import dedupliziert.
      +6 Tests (test_db_resilience.py, Fake-Pool). start.sh-PID-Bug (Punkt 15) mit erledigt.
- [ ] 2. core/tools.py (262) + core/agent.py (198)
- [ ] 3. core/message_handler.py (258) + orchestrator.py (279) + core/idle_loop.py (270)
- [ ] 4. core/autopilot.py (887) — größtes Modul
- [ ] 5. memory/ (extractor 342, lzg 337, knowledge 336)
- [ ] 6. core/skill_factory.py (242) + core/skill_md.py (197) + core/eval_suite.py (195)
- [ ] 7. domains/fitness.py (555) + web/routers/fitness.py (316)
- [ ] 8. domains/second_brain.py (444) + task_executor.py (425)
- [ ] 9. domains/ Rest (calendar, gcal_writer, goals, health, pattern_detector, insight_engine)
- [ ] 10. communication/telegram.py (474)
- [ ] 11. web/routers/ Rest (nutrition 282, system 241, tasks 188, …)
- [ ] 12. tools/ (url_handler 267, search 203) + llm/ (local 190, backends/claude 185)
- [ ] 13. main.py (177) + proactive.py (338) + thermal.py (181) + core/ui_state.py (355)
- [ ] 14. Global-Sweep: stumme excepts sichten (loggen oder begründen), prints → logging
- [x] 15. start.sh PID-Bug gefixt (killt beide PID-Dateien, schreibt nur noch mantis_pid.txt)

## Log
- (noch nichts abgeschlossen)
