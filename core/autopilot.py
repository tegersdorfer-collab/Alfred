"""
Autopilot – die autonome Engine von Alfred.
Zeitbewusste, wertorientierte proaktive Aktivitäten statt simpler Zufallsgedanken:

- Morgen-Briefing (Wetter, Termine, Tasks, Habits, Ziel-Fokus)
- Abend-Review (Tagesrückblick, Mood-Check, Plan für morgen)
- Health-Anomalie-Erkennung (Schlaf/HRV-Einbrüche)
- Ziel-Checkins (bei Stillstand)
- Kalender-Vorbereitung (Termin morgen)
- Kontextueller proaktiver Gedanke (mit Selbstbewertung)

Completion-driven: läuft kontinuierlich, dedupliziert Tagesaktivitäten via Settings.
"""
import json
import logging
from datetime import date, datetime, timedelta

from core import db, fast
from core.db import log_event
from domains import habits, fitness, nutrition, goals, journal, weather

log = logging.getLogger(__name__)


class Autopilot:
    def __init__(self, llm, lzg, dashboard, reminders, channel, proactive, tracker,
                 identity: str, lock=None, is_user_active=None, search=None):
        self.llm = llm
        self.lzg = lzg
        self.dashboard = dashboard
        self.reminders = reminders
        self.channel = channel
        self.proactive = proactive
        self.tracker = tracker
        self.identity = identity
        self.lock = lock
        self.is_user_active = is_user_active or (lambda: False)
        self.search = search  # WebSearch-Instanz für Recherche

    # ── Dedup-Helfer (eine Aktivität pro Tag) ────────────────────────────────

    def _needs(self, key: str) -> bool:
        last = db.get_setting(f"autopilot_{key}_date")
        return last != str(date.today())

    def _mark(self, key: str) -> None:
        db.set_setting(f"autopilot_{key}_date", str(date.today()))

    # ── Senden + Persistenz ──────────────────────────────────────────────────

    async def _send(self, text: str, kind: str = "proactive") -> None:
        if not text:
            return
        await self.channel.send(text)
        try:
            self.lzg.save_kzg_turn("assistant", text)
        except Exception:
            pass
        try:
            db.execute(
                "INSERT INTO chat_messages (role, content, channel, meta) VALUES (%s,%s,'autopilot',%s)",
                ("assistant", text, json.dumps({"kind": kind})),
            )
        except Exception:
            pass
        log_event(kind, text[:120])
        self.tracker.record_sent()

    # ── Haupt-Tick ────────────────────────────────────────────────────────────

    async def tick(self) -> bool:
        """Ein autonomer Schritt. Gibt True zurück wenn etwas gesendet wurde."""
        # 1. Fällige Reminder (zeitkritisch, immer – auch wenn User gerade aktiv)
        sent_reminder = False
        try:
            for r in self.reminders.get_due():
                await self._send(f"⏰ Erinnerung: {r.text}", kind="reminder")
                sent_reminder = True
        except Exception as e:
            log.debug(f"Reminder-Check: {e}")
        if sent_reminder:
            return True

        # Wenn Timo gerade aktiv ist: Modell für ihn freihalten, keine proaktive Last
        if self.is_user_active():
            return False

        hour = datetime.now().hour

        # 2. Morgen-Briefing (erst ab 6:35 – Health-Daten kommen um 6:30 rein)
        now_dt = datetime.now()
        if (now_dt.hour > 6 or (now_dt.hour == 6 and now_dt.minute >= 35)) and hour < 11 and self._needs("briefing"):
            try:
                async with self._guard():
                    await self._morning_briefing()
                self._mark("briefing")
                return True
            except Exception as e:
                log.warning(f"Briefing fehlgeschlagen: {e}")

        # 2b. Kalender-Optimierung morgens (nach Briefing, 1x/Tag)
        if (now_dt.hour > 6 or (now_dt.hour == 6 and now_dt.minute >= 35)) and hour < 11 and self._needs("cal_optimize"):
            try:
                async with self._guard():
                    await self._calendar_check()
                self._mark("cal_optimize")
                return True
            except Exception as e:
                log.warning(f"Kalender-Optimierung fehlgeschlagen: {e}")

        # 3. Abend-Review
        if 19 <= hour < 23 and self._needs("review"):
            try:
                async with self._guard():
                    await self._evening_review()
                self._mark("review")
                return True
            except Exception as e:
                log.warning(f"Review fehlgeschlagen: {e}")

        # 4. Health-Anomalie (tagsüber, einmal/Tag)
        if 8 <= hour < 21 and self._needs("health_alert"):
            try:
                async with self._guard():
                    msg = await self._health_anomaly()
                if msg:
                    await self._send(msg, kind="health")
                self._mark("health_alert")
                if msg:
                    return True
            except Exception as e:
                log.debug(f"Health-Anomalie: {e}")

        # 5. Alfred-Tasks abarbeiten (Deep Execution)
        try:
            active = db.query(
                """SELECT * FROM tasks WHERE assigned_to='alfred'
                   AND status NOT IN ('done','archived')
                   AND (suggestion_status IS NULL OR suggestion_status='accepted')
                   AND (hold_until IS NULL OR hold_until < NOW())
                   ORDER BY
                     CASE execution_phase
                       WHEN 'executing' THEN 0
                       WHEN 'pending'   THEN 1
                       ELSE 2
                     END,
                     priority DESC, created_at ASC
                   LIMIT 1"""
            )
            if active:
                task = active[0]
                async with self._guard():
                    await self._deep_execute_tick(task)
                return True
        except Exception as e:
            log.warning(f"Task-Executor: {e}")

        # 7. Kontextueller proaktiver Gedanke (mit Mindestabstand + Selbstbewertung)
        if not self.tracker.can_send():
            return False
        async with self._guard():
            if self.is_user_active():
                return False
            thought = await self.proactive.generate()
            if not thought:
                return False
            if await self.proactive.evaluate(thought):
                await self._send(thought, kind="thought")
                return True
            log_event("thought", f"verworfen: {thought[:80]}")
            return False

    async def _deep_execute_tick(self, task: dict) -> None:
        """Ein Tick der Deep-Execution: Planning → Clarification → Subtask → Finalize."""
        from domains.task_executor import plan_task, execute_next_subtask, finalize_task
        from core.status import BUS
        phase = task.get("execution_phase") or "pending"
        tid = task["id"]
        title_short = task["title"][:40] + ("…" if len(task["title"]) > 40 else "")

        # ── Phase 1: Planning ──────────────────────────────────────────────────
        if phase == "pending":
            log.info(f"📋 Plane Task: {task['title']}")
            BUS.emit("task_working", f"📋 Plant: {title_short}")
            db.execute("UPDATE tasks SET execution_phase='planning', status='in_progress' WHERE id=%s", (tid,))
            plan = await plan_task(task, self.llm, self.lzg)

            # Unteraufgaben anlegen
            for i, s in enumerate(plan.get("subtasks", [])):
                import json as _json
                notes_payload = _json.dumps({
                    "title": s["title"],
                    "needs_research": s.get("needs_research", False),
                    "research_query": s.get("research_query"),
                }, ensure_ascii=False)
                db.execute(
                    "INSERT INTO tasks (title, notes, parent_id, assigned_to, sort_order, status) VALUES (%s,%s,%s,'alfred',%s,'todo')",
                    (s["title"], notes_payload, tid, i)
                )

            # Rückfrage nötig?
            if plan.get("clarification_needed") and plan.get("clarification_question"):
                q = plan["clarification_question"]
                db.execute(
                    "UPDATE tasks SET execution_phase='waiting_clarification', clarification_question=%s, hold_until=NOW() + INTERVAL '24 hours' WHERE id=%s",
                    (q, tid)
                )
                await self._send(
                    f"❓ Zu deiner Aufgabe **{task['title']}**:\n\n{q}\n\n_(Antworte einfach hier – ich mache danach weiter)_",
                    kind="task_clarification"
                )
                log.info(f"🤔 Warte auf Klärung: {task['title']}")
            else:
                db.execute("UPDATE tasks SET execution_phase='executing' WHERE id=%s", (tid,))
                log.info(f"▶️  Starte Ausführung: {task['title']} ({len(plan.get('subtasks',[]))} Schritte)")

        # ── Phase 2: Warten auf Antwort ────────────────────────────────────────
        elif phase == "waiting_clarification":
            # Antwort ist in clarification_answer (gesetzt vom Message-Handler)
            if task.get("clarification_answer"):
                db.execute("UPDATE tasks SET execution_phase='executing', hold_until=NULL WHERE id=%s", (tid,))
                log.info(f"✅ Klärung erhalten, weiter: {task['title']}")
            # sonst einfach warten (hold_until läuft nach 24h ab → macht ohne Antwort weiter)
            elif not task.get("hold_until") or datetime.now().timestamp() > task.get("hold_until", datetime.now()).timestamp():
                db.execute("UPDATE tasks SET execution_phase='executing', hold_until=NULL WHERE id=%s", (tid,))

        # ── Phase 3: Schritt für Schritt ausführen ─────────────────────────────
        elif phase == "executing":
            # Nächsten Schritt für Status ermitteln
            next_sub = db.query(
                "SELECT title FROM tasks WHERE parent_id=%s AND status NOT IN ('done','archived') ORDER BY sort_order ASC, id ASC LIMIT 1",
                (tid,)
            )
            done_count = len(db.query("SELECT 1 FROM tasks WHERE parent_id=%s AND status='done'", (tid,)))
            total_count = len(db.query("SELECT 1 FROM tasks WHERE parent_id=%s", (tid,)))
            step_info = f"{done_count+1}/{total_count}" if total_count else ""
            sub_title = next_sub[0]["title"][:30] if next_sub else "…"
            BUS.emit("task_working", f"🤖 {step_info} {sub_title}")
            search = self.search
            more = await execute_next_subtask(task, self.llm, search=search)
            if not more:
                # Alle Schritte fertig → synthese
                db.execute("UPDATE tasks SET execution_phase='finalizing' WHERE id=%s", (tid,))

        # ── Phase 4: Zusammenfassen & senden ──────────────────────────────────
        elif phase == "finalizing":
            BUS.emit("task_working", f"✍️ Fasst zusammen: {title_short}")
            result = await finalize_task(task, self.llm)
            db.execute(
                "UPDATE tasks SET status='done', execution_phase='done', completed_at=NOW(), alfred_result=%s WHERE id=%s",
                (result[:4000], tid)
            )
            # Kurze Zusammenfassung senden
            preview = result[:600] + ("…" if len(result) > 600 else "")
            await self._send(
                f"✅ **{task['title']}** erledigt\n\n{preview}\n\n_(Vollständiges Ergebnis im Hub unter Aufgaben)_",
                kind="task_result"
            )
            log.info(f"🎉 Task abgeschlossen: {task['title']}")

    def _guard(self):
        """Context-Manager: nutzt den geteilten LLM-Lock falls vorhanden."""
        import contextlib
        if self.lock is not None:
            return self.lock
        return contextlib.nullcontext()

    # ── Aktivitäten ────────────────────────────────────────────────────────────

    async def _gather(self) -> dict:
        """Sammelt Live-Kontext (parallel-tauglich, hier sequentiell weil DB sync)."""
        ctx = {}
        try:
            ctx["health"] = self.dashboard.get_recent_health(days=2)
        except Exception:
            ctx["health"] = []
        try:
            ctx["events"] = self.dashboard.get_upcoming_events(days=2)
        except Exception:
            ctx["events"] = []
        try:
            ctx["tasks"] = self.dashboard.get_open_tasks(limit=6)
        except Exception:
            ctx["tasks"] = []
        try:
            ctx["habits"] = habits.habit_overview()
        except Exception:
            ctx["habits"] = []
        try:
            ctx["goals"] = goals.list_goals()
        except Exception:
            ctx["goals"] = []
        try:
            ctx["weather"] = await weather.get_weather()
        except Exception:
            ctx["weather"] = None
        try:
            mems = self.lzg.get_all(limit=8)
            ctx["memories"] = self.lzg.format_for_context(mems)
        except Exception:
            ctx["memories"] = ""
        return ctx

    async def _morning_briefing(self) -> None:
        ctx = await self._gather()
        lines = []
        if ctx["weather"] and not ctx["weather"].get("error"):
            n = ctx["weather"]["now"]
            today = ctx["weather"]["forecast"][0] if ctx["weather"]["forecast"] else {}
            lines.append(f"Wetter: {n['temp']}°C, {n['desc']}; heute {today.get('min')}–{today.get('max')}°C, Regen {today.get('rain_prob')}%")
        if ctx["events"]:
            today_date = date.today()
            tomorrow_date = today_date + timedelta(days=1)
            event_parts = []
            for e in ctx["events"][:5]:
                e_date = e.start.date() if hasattr(e.start, "date") else e.start
                if e_date == today_date:
                    day_label = "heute"
                elif e_date == tomorrow_date:
                    day_label = "morgen"
                else:
                    day_label = e_date.strftime("%d.%m.")
                time_str = "" if e.all_day else f" {e.start.strftime('%H:%M')} Uhr"
                event_parts.append(f"{day_label}{time_str}: {e.title}")
            lines.append("Termine: " + "; ".join(event_parts))
        if ctx["tasks"]:
            lines.append("Top-Aufgaben: " + "; ".join(t.title for t in ctx["tasks"][:4]))
        if ctx["habits"]:
            offen = [h["name"] for h in ctx["habits"] if not h["today_done"]]
            if offen:
                lines.append("Offene Gewohnheiten heute: " + ", ".join(offen))
        if ctx["health"]:
            h = ctx["health"][0]
            if h.sleep_duration:
                lines.append(f"Letzte Nacht: {h.sleep_duration:.1f}h Schlaf")
        if ctx["goals"]:
            lines.append("Ziele: " + "; ".join(f"{g['title']} ({g['progress_pct']}%)" for g in ctx["goals"][:3]))

        facts = "\n".join(lines) if lines else "Keine besonderen Daten."
        prompt = (
            f"{self.identity}\n\n"
            "Erstelle ein kurzes, energetisches Morgen-Briefing für Timo auf Deutsch. "
            "Max 5-6 Zeilen. Konkret, motivierend, kein Smalltalk. "
            "Beginne mit 'Guten Morgen'. Hebe das Wichtigste hervor und gib einen klaren Fokus für den Tag. "
            "Schreibe jeden Punkt nur EINMAL. Keine Wiederholungen, keine Selbstkorrekturen.\n\n"
            f"Daten von heute:\n{facts}\n\nBriefing:"
        )
        text = await self.llm.chat(messages=[{"role": "user", "content": prompt}],
                                   temperature=0.6, max_tokens=300)
        await self._send("☀️ " + text.strip(), kind="briefing")
        log.info("☀️ Morgen-Briefing gesendet")

    async def _evening_review(self) -> None:
        ctx = await self._gather()
        # Tagesleistung sammeln
        done_habits = [h["name"] for h in ctx["habits"] if h["today_done"]]
        open_habits = [h["name"] for h in ctx["habits"] if not h["today_done"]]
        try:
            workouts_today = [w for w in fitness.recent_workouts(5) if str(w["date"]) == str(date.today())]
        except Exception:
            workouts_today = []
        nut = nutrition.day_totals()

        lines = []
        if done_habits:
            lines.append(f"Erledigte Gewohnheiten: {', '.join(done_habits)}")
        if open_habits:
            lines.append(f"Nicht erledigt: {', '.join(open_habits)}")
        if workouts_today:
            lines.append(f"Training: {', '.join(w['title'] for w in workouts_today)}")
        if nut.get("kcal"):
            lines.append(f"Ernährung: {int(nut['kcal'])} kcal, {int(nut['protein'])}g Protein")
        if ctx["events"]:
            tomorrow = [e for e in ctx["events"]
                        if e.start.date() == date.today() + timedelta(days=1)]
            if tomorrow:
                lines.append("Morgen: " + "; ".join(e.title for e in tomorrow[:3]))

        facts = "\n".join(lines) if lines else "Wenig Daten erfasst."
        prompt = (
            f"{self.identity}\n\n"
            "Erstelle einen kurzen Abend-Review für Timo auf Deutsch. Max 4-5 Zeilen. "
            "Würdige kurz was lief, sprich offen an was liegen blieb (direkt, respektvoll). "
            "Stelle GENAU EINE konkrete Frage zum Tag. "
            "Schreibe jeden Punkt nur EINMAL. Keine Wiederholungen, keine Entschuldigungen.\n\n"
            f"Tagesdaten:\n{facts}\n\nReview:"
        )
        text = await self.llm.chat(messages=[{"role": "user", "content": prompt}],
                                   temperature=0.6, max_tokens=300)
        await self._send("🌙 " + text.strip(), kind="review")
        log.info("🌙 Abend-Review gesendet")

    async def _health_anomaly(self) -> str | None:
        """Erkennt auffällige Health-Werte und formuliert ggf. einen Hinweis."""
        health = self.dashboard.get_recent_health(days=5)
        if len(health) < 2:
            return None
        latest = health[0]
        flags = []
        # Schlaf
        sleeps = [h.sleep_duration for h in health if h.sleep_duration]
        if latest.sleep_duration and len(sleeps) >= 2:
            avg = sum(sleeps[1:]) / max(1, len(sleeps[1:]))
            if latest.sleep_duration < 6 and latest.sleep_duration < avg - 1:
                flags.append(f"nur {latest.sleep_duration:.1f}h Schlaf (Schnitt {avg:.1f}h)")
        # HRV
        hrvs = [h.hrv for h in health if h.hrv]
        if latest.hrv and len(hrvs) >= 3:
            avg_hrv = sum(hrvs[1:]) / max(1, len(hrvs[1:]))
            if latest.hrv < avg_hrv * 0.8:
                flags.append(f"HRV deutlich gesunken ({latest.hrv:.0f} vs. Schnitt {avg_hrv:.0f})")
        # Ruhepuls
        hrs = [h.resting_hr for h in health if h.resting_hr]
        if latest.resting_hr and len(hrs) >= 3:
            avg_hr = sum(hrs[1:]) / max(1, len(hrs[1:]))
            if latest.resting_hr > avg_hr + 7:
                flags.append(f"erhöhter Ruhepuls ({latest.resting_hr} vs. {avg_hr:.0f})")
        if not flags:
            return None
        prompt = (
            f"{self.identity}\n\n"
            "Formuliere einen kurzen Hinweis (2-3 Sätze) zu Timos Gesundheit. "
            "Sachlich, kein Alarmismus, ein konkreter Vorschlag. "
            "Schreibe jeden Satz nur EINMAL.\n\n"
            f"Auffälligkeiten: {'; '.join(flags)}\n\nHinweis:"
        )
        text = await self.llm.chat(messages=[{"role": "user", "content": prompt}],
                                   temperature=0.5, max_tokens=150)
        return "🩺 " + text.strip()

    async def _calendar_check(self) -> None:
        """Analysiert den heutigen Tagesplan und meldet Konflikte / Vorschläge."""
        from domains.calendar_optimizer import analyze_day
        ctx = await self._gather()
        events = ctx.get("events", [])
        if not events:
            return
        result = await analyze_day(events, self.llm)
        summary = result.get("summary", "")
        if not summary or summary == "Plan sieht gut aus." or "Keine Termine" in summary:
            log.debug("Kalender-Check: kein Handlungsbedarf")
            return
        await self._send("📅 " + summary, kind="calendar_check")
        log.info("📅 Kalender-Check gesendet")
