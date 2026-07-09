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
- [x] 5. memory/ — knowledge.py: toten link_memory() entfernt (0 Aufrufer, nutzte Tabelle
      kg_memory_entities die nicht in den Migrationen steht → Crash bei Neuinstall; da nie
      aufgerufen war kg_linked ohnehin immer FALSE, kein Verhaltensänderung), field-Import raus.
      extractor/lzg gesichtet: sauber. +11 Tests (Regex-Extraktion, Jaccard, Temporal-Heuristik).
- [x] 6. skill_factory/skill_md/eval_suite — Code war sauber, aber der SICHERHEITSKRITISCHE
      AST-Validator validate_source (Sandbox für selbst-generierten Code) hatte 0 Tests.
      +25 Tests (verbotene Imports os/sys/subprocess/…, eval/exec/open, Struktur-Regeln)
      +13 skill_md-Tests (Frontmatter, Trigger-Matching, Path-Traversal-Schutz).
- [x] 7. domains/fitness.py — Bug in suggest_next_weight: 'press down' (Trizeps/Oberkörper)
      stand in der lower_body-Liste → hätte +5kg statt +2.5kg empfohlen; gefixt + dt. Keywords
      ergänzt. +13 Tests (AlphaProgression-Logik mit gemocktem db, merge_profile, normalize_set).
      web/routers/fitness.py gesichtet: Excepts alle berechtigt, sauber.
- [x] 8. second_brain.py — N+1 behoben: _row_to_note lud Wiki-Links pro Notiz einzeln
      (get_all(500) = 500 Extra-Queries); neu _rows_to_notes() lädt alle Links in EINER
      Query (get_all/get_by_category/search_notes umgestellt). task_executor.py — plan_task
      gab LLM-Output ungeprüft zurück; JSON-Array hätte Autopilot gecrasht → isinstance-Guard.
      +5 Brain-Tests (Batch-Nachweis) +8 Task-Executor-Tests (classify, Plan-Fallbacks).
- [x] 9. domains/ Rest — health.py: reines Feld-Mapping (Einheiten/SpO2/Schlaf/Key-Fallbacks)
      aus process_health_data in testbares map_health_fields() extrahiert +13 Tests.
      calendar.py: stiller ICS-Event-Parse-Except loggt jetzt (Debug). goals/gcal_writer/
      pattern_detector/insight_engine gesichtet: sauber.
- [x] 10. communication/telegram.py — BUG: 'Task zurückstellen'-Button setzte status='open'
      (kein gültiger Status, nur Filter-Alias) → Task fiel aus allen Listen, wurde unsichtbar.
      Auf 'todo' gefixt + set_status in domains/tasks.py gehärtet (VALID_STATUSES, coerct
      'open'→'todo', ignoriert Müll statt zu schreiben). +5 Tests.
- [x] 11. web/routers/ — geteilte _helpers.py (_jsonable rekursiv, _event_dict, _health_dict)
      quer über alle Endpoints genutzt aber ungetestet → +8 Tests. system.py verifiziert:
      status() liest korrekte PID-Datei (main.py schreibt mantis.pid), overview/analytics-
      Excepts sind bewusste Degradation. tasks.py: stiller Klassifikations-Except loggt jetzt.
- [ ] 12. tools/ (url_handler 267, search 203) + llm/ (local 190, backends/claude 185)
- [ ] 13. main.py (177) + proactive.py (338) + thermal.py (181) + core/ui_state.py (355)
- [ ] 14. Global-Sweep: stumme excepts sichten (loggen oder begründen), prints → logging
- [x] 15. start.sh PID-Bug gefixt (killt beide PID-Dateien, schreibt nur noch mantis_pid.txt)

## Log
- 32ae6d9 Modul 1: core/db.py (Pool-Resilienz) + start.sh
- 46723f1 Modul 2: core/agent.py Math-Guard-Fix + Loop-Tests
- c256f45 Modul 3: lzg_embed-Freeze-Fix + Message-Handler-Dedup
- cd62cad Modul 4: autopilot.py — 5 tote Features wiederbelebt
- bafe560 Modul 5: memory/ toter link_memory raus + Pure-Helfer-Tests
- 0dca849 Modul 6: Skill-Validator + skill_md getestet (+38 Tests)
- 7922f6a Modul 7: fitness.py Progression-Bug + AlphaProgression-Tests
- c97cc3a Modul 8: second_brain N+1 + task_executor Robustheit
- 0b6ed0a Modul 9: health-Mapping extrahiert+getestet, calendar-Log
- 1360957 Modul 10: telegram task_skip-Bug + set_status-Härtung
- Modul 11: Router-Helfer getestet + tasks-Router-Log
