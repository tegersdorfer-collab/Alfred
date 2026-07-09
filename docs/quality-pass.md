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
- [x] 2. core/tools.py (sauber, keine Änderung nötig) + core/agent.py — Math-Guard-Bug
      gefixt (continue verwarf Retry-Tool-Calls → Extra-LLM-Call), +7 ReAct-Loop-Tests
      mit FakeBackend (test_agent_loop.py).
- [x] 3. message_handler — Telegram/Dashboard-Duplikation auf gemeinsamen _agent_turn/
      _finish_turn-Kern gezogen, stumme Persist-Excepts loggen jetzt. orchestrator —
      lzg_embed-Bug gefixt (fror Event-Loop 10s ein bzw. lieferte im Threadpool immer []),
      Haupt-Loop-Referenz in start(). brain-Router: add/update_note via to_thread.
      idle_loop gesichtet: ok. +3 Tests (test_lzg_embed.py).
- [x] 4. core/autopilot.py — 5 tote Features wiederbelebt (alle von except:pass versteckt):
      Newsletter-Tasks+Reflexions-Tasks (tasks.updated_at existiert nicht → completed_at),
      Newsletter-Habits + Stale-Habit-Warnung (habit_logs.done_on → date), KI-Reflexion→
      Brain (BrainNote-Dataclass als Dict indexiert), Weather-Coaching (falsche API-Keys
      temp_c/description → now.temp/now.desc), frische LZG()-Instanz → self.lzg.
      Stumme Excepts in Newsletter/Smart-Notify loggen jetzt. Tote Imports raus.
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
- 32ae6d9 Modul 1: core/db.py (Pool-Resilienz) + start.sh
- 46723f1 Modul 2: core/agent.py Math-Guard-Fix + Loop-Tests
- c256f45 Modul 3: lzg_embed-Freeze-Fix + Message-Handler-Dedup
- Modul 4: autopilot.py — 5 tote Features wiederbelebt
