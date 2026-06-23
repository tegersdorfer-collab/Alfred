"""
IdleLoop — Autopilot-Ticks, Maintenance, Health-Refresh, Pattern-Detection, Monitoring.
Läuft als asyncio-Task wenn kein aktives Gespräch stattfindet.
"""
import asyncio
import logging
from datetime import datetime

from core import db, backup
from core.status import BUS

log = logging.getLogger(__name__)


def _safe_task(coro, label: str):
    async def _wrapper():
        try:
            await coro
        except Exception as e:
            log.warning(f"Background-Task '{label}' fehlgeschlagen: {e}", exc_info=True)
            db.log_error(label, e)
    return asyncio.create_task(_wrapper())


class IdleLoop:
    def __init__(self, autopilot, reflection, consolidator, forgetting,
                 kzg, lzg, dashboard, thermal, reminders,
                 proactive_engine, proactive_tracker,
                 bg_llm, suggest_one,
                 is_user_active,
                 pattern_detector_mod, generate_insight_task):
        self.autopilot           = autopilot
        self.reflection          = reflection
        self.consolidator        = consolidator
        self.forgetting          = forgetting
        self.kzg                 = kzg
        self.lzg                 = lzg
        self.dashboard           = dashboard
        self.thermal             = thermal
        self.reminders           = reminders
        self.proactive_engine    = proactive_engine
        self.proactive_tracker   = proactive_tracker
        self.bg_llm              = bg_llm
        self.suggest_one         = suggest_one
        self.is_user_active      = is_user_active
        self.pattern_detector    = pattern_detector_mod
        self.generate_insight    = generate_insight_task

        self._state = "idle"
        self._task: asyncio.Task | None = None

        self._last_consolidation: datetime | None = None
        self._last_health_refresh: datetime | None = None
        self._last_health_suggestion: datetime | None = None
        self._last_pattern_run: datetime | None = None
        self._last_insight_run: datetime | None = None

    def resume(self) -> None:
        self._state = "idle"
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self._loop())

    def pause(self) -> None:
        self._state = "conversation"
        if self._task and not self._task.done():
            self._task.cancel()

    # ── Main Loop ─────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        await asyncio.sleep(20)
        while self._state == "idle":
            try:
                thermal_state = self.thermal.get_state()
                if thermal_state.paused:
                    await self.thermal.wait_until_cool()
                    continue
            except Exception as e:
                log.debug(f"Thermal-Check: {e}")

            await self._tick_autopilot()

            if not self.is_user_active():
                await self._tick_reflection()
                await self._tick_maintenance()
                await self._tick_health()
                await self._tick_patterns()
                await self._tick_insights()

            await asyncio.sleep(self._next_delay())

    # ── Ticks ─────────────────────────────────────────────────────────────────

    async def _tick_autopilot(self) -> None:
        try:
            await self.autopilot.tick()
        except Exception as e:
            log.debug(f"Autopilot-Tick: {e}")
            db.log_error("Autopilot-Tick", e)

    async def _tick_reflection(self) -> None:
        try:
            await self.reflection.daily_reflection()
        except Exception as e:
            log.debug(f"Reflexion: {e}")
            db.log_error("Reflexion", e)

    async def _tick_maintenance(self) -> None:
        now = datetime.now()
        if self._last_consolidation and (now - self._last_consolidation).total_seconds() < 3600:
            await self._maybe_kzg_checkpoint()
            return
        self._last_consolidation = now
        for coro, label in [
            (self.consolidator.consolidate_silent(), "Memory-Consolidator"),
            (self._run_forgetting(), "ForgettingCurve"),
            (asyncio.to_thread(backup.maybe_run_daily), "DB-Backup"),
        ]:
            try:
                await coro
            except Exception as e:
                log.debug(f"{label}: {e}")
                db.log_error(label, e)
        await self._maybe_kzg_checkpoint()

    async def _maybe_kzg_checkpoint(self) -> None:
        if not self.kzg.should_checkpoint():
            return
        turns = self.kzg.get_turns_for_summary()
        if not turns:
            return
        lines = "\n".join(
            f"{'Timo' if t.role == 'user' else 'Alfred'}: {t.content}" for t in turns
        )
        prompt = (
            "Fasse das folgende Gespräch prägnant auf Deutsch zusammen (max 200 Wörter). "
            "Behalte wichtige Fakten, Entscheidungen und Aufgaben.\n\n" + lines
        )
        try:
            summary = await self.bg_llm.complete(prompt, max_tokens=300)
            self.kzg.apply_checkpoint(summary, len(turns))
            log.info(f"📝 KZG-Checkpoint: {len(turns)} Turns komprimiert")
        except Exception as e:
            log.warning(f"KZG-Checkpoint fehlgeschlagen: {e}")

    async def _run_forgetting(self) -> None:
        stats = await self.forgetting.run()
        if stats["forgotten"] or stats["chat_pruned"]:
            log.info(f"🕐 Forgetting: {stats}")

    async def _tick_health(self) -> None:
        now = datetime.now()
        since = (now - self._last_health_refresh).total_seconds() if self._last_health_refresh else 1801
        if since < 1800:
            return
        self._last_health_refresh = now
        try:
            new_days = await asyncio.to_thread(self.dashboard.refresh_health)
            if not new_days or not self.proactive_tracker.can_send_data_event():
                return
            thought = await self.proactive_engine.generate()
            if thought and await self.proactive_engine.evaluate(thought):
                await self.autopilot._send(thought, kind="health_update")
                self.proactive_tracker.record_sent()
            since_sug = (now - self._last_health_suggestion).total_seconds() if self._last_health_suggestion else 86401
            if since_sug > 86400:
                ok = await self.suggest_one(
                    f"Neue Gesundheitsdaten für {new_days} Tag(e) importiert",
                    self.bg_llm, self.lzg
                )
                if ok:
                    self._last_health_suggestion = now
        except Exception as e:
            log.debug(f"Health-Refresh: {e}")
            db.log_error("Health-Refresh", e)

    async def _tick_patterns(self) -> None:
        now = datetime.now()
        if self._last_pattern_run and (now - self._last_pattern_run).total_seconds() < 86400:
            return
        self._last_pattern_run = now
        try:
            n = await self.pattern_detector.update_memories(self.lzg, self.bg_llm)
            if n:
                log.info(f"🔍 Pattern Detector: {n} neue Muster gespeichert")
        except Exception as e:
            log.debug(f"Pattern Detector: {e}")
            db.log_error("Pattern-Detector", e)

    async def _tick_insights(self) -> None:
        now = datetime.now()
        since = (now - self._last_insight_run).total_seconds() if self._last_insight_run else 14401
        if since < 14400:
            return
        has_active = db.query(
            "SELECT 1 FROM tasks WHERE assigned_to='alfred' AND status NOT IN ('done','archived') "
            "AND (suggestion_status IS NULL OR suggestion_status='accepted') LIMIT 1"
        )
        if has_active:
            return
        self._last_insight_run = now
        try:
            await self.generate_insight(self.bg_llm, self.lzg)
        except Exception as e:
            log.debug(f"Insight-Engine: {e}")
            db.log_error("Insight-Engine", e)

    # ── Monitoring ────────────────────────────────────────────────────────────

    async def monitoring_loop(self) -> None:
        import httpx as _httpx
        import config
        _failures = 0
        await asyncio.sleep(60)
        while True:
            try:
                async with _httpx.AsyncClient(timeout=5) as c:
                    port = getattr(config, "DASHBOARD_PORT", 7779)
                    r = await c.get(f"http://127.0.0.1:{port}/health")
                checks = r.json() if r.status_code == 200 else {}
                unhealthy = [k for k, v in checks.items() if str(v).startswith("error")]
                if unhealthy:
                    _failures += 1
                    if _failures >= 2:
                        msg = f"⚠️ Alfred Health-Check: {', '.join(unhealthy)} fehlerhaft"
                        try:
                            from core.push import send_push
                            await asyncio.to_thread(send_push, "Alfred Health Alert", msg)
                        except Exception:
                            pass
                        log.warning(msg)
                else:
                    _failures = 0
            except Exception as e:
                log.debug(f"Monitoring: {e}")
            await asyncio.sleep(300)

    # ── Delay ─────────────────────────────────────────────────────────────────

    def _next_delay(self) -> int:
        try:
            nxt = self.reminders.next_due_seconds()
        except Exception:
            nxt = None
        has_active = db.query(
            "SELECT 1 FROM tasks WHERE assigned_to='alfred' AND status='in_progress' "
            "AND execution_phase IN ('executing','finalizing') LIMIT 1"
        )
        if has_active:
            return 8
        return 60 if nxt is None else max(5, min(60, nxt + 1))
